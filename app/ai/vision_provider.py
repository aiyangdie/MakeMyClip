# -*- coding: utf-8 -*-
"""视觉识别：可替换接口 + 本地启发式实现（阶段三）。

最高原则（对应任务书"商品保护原则"）：
1. 绝不把文件名当作识别结论——本模块读取的是视频真实帧。
2. 绝不臆造图像测不出的语义（拉手/灯罩材质/承重/色温具体数值）。
3. 只输出"能从画面真实测量到的线索"，每条带置信度 + 证据 + 是否需人工核验。
4. 语义标签由 storyboard_matcher 依据可配置规则从"线索"推断，推断不出来就报缺失。

本地实现能可靠测量的线索：
- 灯光状态数量与切换（用暖冷比 warmness 区分色温变化 vs 纯亮度/曝光变化）
- 画面运动能量曲线（开合/旋转/升降类往复运动的"有运动"信号）
- 手部/前景遮挡占比
- 明暗与色彩丰富度、边缘密度、主体大致占比

不能可靠测量、必须留给视觉大模型或人工的：
- 拉手、灯罩、柜脚、台面材质、实体开关等具体部件
- 抽屉是否"完整开合"、灯头是否"真的旋转"、灯杆是否"真的升降"
- 三色温的具体色温值

替换方式：继承 BaseVisionProvider 实现 analyze_segment()，在 provider_factory 注册即可。
"""
import cv2
import numpy as np

from .. import media

# 视觉线索代码（稳定常量，matcher 依赖这些 code）
CUE_LIGHT_STATES = "light_states"        # 观察到 N 种灯光状态
CUE_LIGHT_SWITCH = "light_switch"        # 观察到明确的灯光切换动作
CUE_EXPOSURE_ONLY = "exposure_only"      # 疑似仅曝光变化（非色温）
CUE_MOTION = "motion"                    # 观察到画面运动
CUE_RECIPROCATING = "reciprocating"      # 往复式开合/移动模式
CUE_HAND = "hand"                        # 画面中出现手/前景
CUE_SUBJECT_CLOSE = "subject_close"      # 主体占比大（近景/特写）
CUE_SUBJECT_WHOLE = "subject_whole"      # 主体占比适中、轮廓完整（整体视角）

ALL_CUES = [CUE_LIGHT_STATES, CUE_LIGHT_SWITCH, CUE_EXPOSURE_ONLY, CUE_MOTION,
            CUE_RECIPROCATING, CUE_HAND, CUE_SUBJECT_CLOSE, CUE_SUBJECT_WHOLE]


class BaseVisionProvider:
    """所有视觉识别实现必须继承此类。接口稳定，可替换。"""

    name = "base"

    def analyze_segment(self, path, start_ms, end_ms, progress_cb=None):
        """分析一个片段，返回统一结构的 dict（见 HeuristicVisionProvider）。"""
        raise NotImplementedError


def _cue(code, name, confidence, evidence, need_review=False):
    return {
        "code": code, "name": name,
        "confidence": round(float(confidence), 2),
        "evidence": evidence,
        "need_review": bool(need_review),
    }


class HeuristicVisionProvider(BaseVisionProvider):
    """本地启发式实现：不联网、不需要模型，只做真实图像测量。"""

    name = "heuristic_local_v1"

    def __init__(self, sample_interval_ms=250, max_samples=40):
        self.sample_interval_ms = sample_interval_ms
        self.max_samples = max_samples

    # ---------- 帧采样 ----------
    def _sample_frames(self, path, start_ms, end_ms, progress_cb=None):
        proxy = media.preview_link(path)
        cap = cv2.VideoCapture(proxy)
        if not cap.isOpened():
            return []
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        start_f = max(0, int(start_ms / 1000.0 * fps))
        end_f = max(start_f + 1, int(end_ms / 1000.0 * fps))
        step = max(1, int(fps * self.sample_interval_ms / 1000.0))
        # 控制采样数量上限
        span = end_f - start_f
        if span // step > self.max_samples:
            step = max(step, span // self.max_samples)
        frames = []
        idx = start_f
        while idx < end_f:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, fr = cap.read()
            if not ok:
                break
            frames.append((int(idx / fps * 1000), fr))
            if progress_cb:
                progress_cb(idx - start_f, end_f - start_f)
            idx += step
        cap.release()
        return frames

    # ---------- 单帧指标 ----------
    @staticmethod
    def _frame_metrics(frame):
        small = cv2.resize(frame, (160, 90))
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        brightness = float(np.mean(gray)) / 255.0            # 明度 0..1
        # 暖冷比：暖光 R 多、冷光 B 多。取画面中较亮像素统计，降低暗部噪点影响
        bright_mask = gray > 60
        if np.count_nonzero(bright_mask) > 50:
            b = float(np.mean(small[:, :, 0][bright_mask]))
            r = float(np.mean(small[:, :, 2][bright_mask]))
            warm = (r - b) / (r + b + 1e-6)                  # 正=偏暖 负=偏冷
        else:
            warm = 0.0
        # 肤色/前景占比（YCrCb 常见肤色区间，仅作"有手/遮挡"的弱证据）
        ycrcb = cv2.cvtColor(small, cv2.COLOR_BGR2YCrCb)
        skin = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
        skin_ratio = float(np.count_nonzero(skin)) / skin.size
        # 边缘密度（构图/清晰度弱指标）
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.count_nonzero(edges)) / edges.size
        # 色彩丰富度
        saturation = float(np.mean(hsv[:, :, 1])) / 255.0
        return {
            "brightness": brightness, "warm": warm,
            "skin_ratio": skin_ratio, "edge_density": edge_density,
            "saturation": saturation, "gray": gray,
        }

    # ---------- 灯光状态聚类 ----------
    @staticmethod
    def _cluster_light_states(items):
        """items: [(t_ms, brightness, warm)] -> 稳定状态列表。

        色温变化会同时改变 warm；纯曝光变化主要改 brightness、warm 基本不变。
        """
        states = []  # {'warm','bright','t0','t1'}
        WARM_TOL, BRIGHT_TOL = 0.05, 0.13
        for t, bright, warm in items:
            hit = None
            for s in states:
                if abs(s["warm"] - warm) <= WARM_TOL and abs(s["bright"] - bright) <= BRIGHT_TOL:
                    hit = s
                    break
            if hit is None:
                states.append({"warm": warm, "bright": bright, "t0": t, "t1": t, "n": 1})
            else:
                # 增量更新中心
                n = hit["n"]
                hit["warm"] = (hit["warm"] * n + warm) / (n + 1)
                hit["bright"] = (hit["bright"] * n + bright) / (n + 1)
                hit["t1"] = t
                hit["n"] = n + 1
        # 合并时间上不连续但特征几乎相同的状态（避免抖动被算成多次）
        merged = []
        for s in states:
            if merged and abs(merged[-1]["warm"] - s["warm"]) <= 0.03 \
                    and abs(merged[-1]["bright"] - s["bright"]) <= 0.06:
                merged[-1]["t1"] = s["t1"]
                merged[-1]["n"] += s["n"]
            else:
                merged.append(s)
        return merged

    # ---------- 主分析 ----------
    def analyze_segment(self, path, start_ms, end_ms, progress_cb=None):
        result = {
            "ok": False, "error": "", "provider": self.name,
            "labels": [], "metrics": {}, "suggested_tags": [],
            "need_review": True, "review_reasons": [],
        }
        frames = self._sample_frames(path, start_ms, end_ms, progress_cb)
        if len(frames) < 3:
            result["error"] = "有效帧不足，无法识别"
            return result

        items = []          # (t, brightness, warm)
        motions = []        # 相邻帧运动能量
        skin_ratios = []
        edge_ds = []
        sats = []
        prev_gray = None
        for t, fr in frames:
            m = self._frame_metrics(fr)
            items.append((t, m["brightness"], m["warm"]))
            skin_ratios.append(m["skin_ratio"])
            edge_ds.append(m["edge_density"])
            sats.append(m["saturation"])
            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, m["gray"])
                motions.append(float(np.mean(diff)) / 255.0)
            prev_gray = m["gray"]

        labels = []

        # --- 灯光状态 ---
        states = self._cluster_light_states(items)
        n_states = len(states)
        warm_span = max((s["warm"] for s in states), default=0) - min((s["warm"] for s in states), default=0)
        bright_span = max((s["bright"] for s in states), default=0) - min((s["bright"] for s in states), default=0)

        result["metrics"]["light_states"] = [
            {"t0_ms": s["t0"], "t1_ms": s["t1"],
             "warm": round(s["warm"], 3), "bright": round(s["bright"], 3)}
            for s in states
        ]
        result["metrics"]["light_state_count"] = n_states
        result["metrics"]["warm_span"] = round(warm_span, 3)
        result["metrics"]["brightness_span"] = round(bright_span, 3)

        if n_states >= 2:
            detail = "；".join(
                f'{s["t0"]/1000:.1f}-{s["t1"]/1000:.1f}s' for s in states)
            if n_states >= 3 and warm_span >= 0.06:
                labels.append(_cue(
                    CUE_LIGHT_STATES, f"观察到 {n_states} 种不同灯光状态",
                    min(0.85, 0.55 + 0.05 * n_states),
                    f"画面出现 {n_states} 个稳定且暖冷比明显不同的状态（跨度{warm_span:.3f}）：{detail}",
                    need_review=False))
                labels.append(_cue(
                    CUE_LIGHT_SWITCH, "疑似三色温/多档灯光切换", 0.6,
                    f"暖冷比在切换点明显变化（跨度{warm_span:.3f}），符合色温切换特征",
                    need_review=True))
                result["suggested_tags"].append("color_temperature")
            elif n_states == 2 and warm_span >= 0.06:
                labels.append(_cue(
                    CUE_LIGHT_STATES, "观察到 2 种不同灯光状态", 0.65,
                    f"暖冷比跨度 {warm_span:.3f}，状态区间：{detail}", need_review=True))
                result["review_reasons"].append("只观察到两种灯光状态，不能直接认定为完整三色温")
            else:
                # 状态差异主要来自亮度而非暖冷比 -> 更像曝光变化
                labels.append(_cue(
                    CUE_EXPOSURE_ONLY, "疑似仅明暗/曝光变化（非色温）", 0.5,
                    f"观察到 {n_states} 个状态，但暖冷比跨度仅 {warm_span:.3f}、亮度跨度 {bright_span:.3f}",
                    need_review=True))
                result["review_reasons"].append("灯光状态差异可能来自曝光，需人工确认是否为真实色温变化")
        else:
            labels.append(_cue(CUE_LIGHT_STATES, "未观察到明显的灯光状态切换", 0.7,
                               "整个片段灯光状态稳定", need_review=False))

        # --- 运动 / 开合 ---
        if motions:
            motion_max = max(motions)
            motion_mean = float(np.mean(motions))
            result["metrics"]["motion_max"] = round(motion_max, 4)
            result["metrics"]["motion_mean"] = round(motion_mean, 4)
            result["metrics"]["motion_curve"] = [round(x, 3) for x in motions]
            if motion_max > 0.03:
                labels.append(_cue(CUE_MOTION, "观察到画面运动", 0.7,
                                   f"相邻帧最大差异 {motion_max:.3f}、平均 {motion_mean:.3f}",
                                   need_review=False))
                # 往复检测：运动能量出现 >=2 个峰且峰间有明显低谷
                hi = sorted(motions)[max(1, len(motions) // 3)]
                peaks = sum(1 for i, v in enumerate(motions)
                            if v > hi and (i == 0 or v >= motions[i - 1])
                            and (i == len(motions) - 1 or v >= motions[i + 1]))
                if peaks >= 2:
                    labels.append(_cue(CUE_RECIPROCATING, "观察到往复式运动模式", 0.5,
                                       f"运动曲线出现约 {peaks} 个峰值，可能是开合/旋转/升降类动作",
                                       need_review=True))
                    result["review_reasons"].append("只测到往复运动，无法确认是抽屉开合还是灯头旋转等具体动作")
            else:
                labels.append(_cue(CUE_MOTION, "画面基本静止", 0.7,
                                   f"相邻帧差异很小（最大 {motion_max:.3f}）", need_review=False))

        # --- 手 / 前景遮挡 ---
        skin_max = max(skin_ratios) if skin_ratios else 0.0
        skin_mean = float(np.mean(skin_ratios)) if skin_ratios else 0.0
        result["metrics"]["skin_ratio_max"] = round(skin_max, 3)
        result["metrics"]["skin_ratio_mean"] = round(skin_mean, 3)
        if skin_max > 0.06:
            # 注意：暖色木质/暖光也可能落入肤色区间，必须标注"疑似+需核验"，不当结论
            labels.append(_cue(CUE_HAND, "疑似出现手/肤色前景", 0.4,
                               f"肤色像素占比最高 {skin_max:.3f}、平均 {skin_mean:.3f}"
                               "（阈值判断，暖色木质/暖光可能误检，需人工核验）",
                               need_review=True))

        # --- 景别（整体 vs 特写，弱信号） ---
        edge_mean = float(np.mean(edge_ds)) if edge_ds else 0.0
        sat_mean = float(np.mean(sats)) if sats else 0.0
        result["metrics"]["edge_density_mean"] = round(edge_mean, 4)
        result["metrics"]["saturation_mean"] = round(sat_mean, 3)
        # 这是很粗的信号，置信度压低并标记需核验
        if edge_mean > 0.10:
            labels.append(_cue(CUE_SUBJECT_CLOSE, "画面细节丰富（可能近景/特写）", 0.4,
                               f"边缘密度 {edge_mean:.3f} 偏高", need_review=True))
        else:
            labels.append(_cue(CUE_SUBJECT_WHOLE, "画面轮廓较完整（可能整体视角）", 0.35,
                               f"边缘密度 {edge_mean:.3f} 偏低、分布较均匀", need_review=True))
        result["review_reasons"].append("景别为弱信号推断，整体/特写需人工看画面确认")

        result["labels"] = labels
        result["need_review"] = any(l["need_review"] for l in labels) or bool(result["review_reasons"])
        result["ok"] = True
        return result


def provider_factory(name=None, prefer_config=True):
    """按名称创建视觉识别实现。

    prefer_config=True 时读取 config/vision.json 的 provider；
    本地 VLM 选中但服务未就绪时，自动降级到启发式（调用方应据 provider.name 标注 UI）。
    """
    from . import vision_config
    cfg = vision_config.load_vision_config()
    chosen = name or (vision_config.active_provider_name(cfg) if prefer_config else None)
    chosen = chosen or HeuristicVisionProvider.name

    if chosen in (HeuristicVisionProvider.name, "heuristic", "local_heuristic"):
        return HeuristicVisionProvider()

    if chosen in ("ollama_qwen_vl", "ollama", "qwen_vl", "vlm", "local"):
        from .ollama_vl_provider import OllamaVLProvider
        local = cfg.get("local") or {}
        prov = OllamaVLProvider(
            base_url=local.get("base_url"),
            model=local.get("model"),
            timeout_sec=local.get("timeout_sec"),
            sample_interval_ms=local.get("sample_interval_ms"),
            max_samples=local.get("max_samples"),
        )
        if prov.ping():
            return prov
        # 降级：返回启发式，但挂上降级标记供 UI 读取
        fb = HeuristicVisionProvider()
        fb.degraded_from = OllamaVLProvider.name
        fb.degrade_reason = "本地视觉模型未就绪，已降级为基础画面测量"
        return fb

    if chosen in ("cloud", "cloud_openai_vl"):
        from .cloud_vl_provider import CloudVLProvider
        cloud = cfg.get("cloud") or {}
        if not cloud.get("enabled"):
            fb = HeuristicVisionProvider()
            fb.degraded_from = "cloud"
            fb.degrade_reason = "云端视觉未启用（cost_cap/开关关闭）"
            return fb
        return CloudVLProvider(cloud)

    # 未知名称 → 启发式
    return HeuristicVisionProvider()
