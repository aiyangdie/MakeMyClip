# -*- coding: utf-8 -*-
"""视频内部镜头切分（阶段二核心）。

设计原则（严格对应计划书）：
- 不按文件切分，不按固定秒数等分。
- 多信号综合：画面直方图差异 + 像素差异 + 边缘结构变化 + 亮度突变。
- 局部峰值 + 自适应阈值，不是单一固定阈值。
- 灯光变亮/变暗、手进入画面、镜头缓慢移动不应被误判为新场景：
  通过"亮度信号单独判定 + 结构信号需同时变化"来抑制这类误报。
- 每个候选边界记录触发信号与分数，可解释。

返回的是"候选镜头边界"，动作语义在阶段三再判断。
"""
import cv2
import numpy as np

from .. import media


def _hist_feature(frame):
    """颜色直方图特征（对亮度做归一化，降低灯光变化的干扰）。"""
    small = cv2.resize(frame, (160, 90))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    # 只用 H/S 通道直方图，跳过 V(亮度)以减少灯光变化误报
    hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def _gray_small(frame):
    small = cv2.resize(frame, (160, 90))
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)


def _edges(gray):
    return cv2.Canny(gray, 50, 150)


def analyze_video(path, sample_interval_ms=400, progress_cb=None):
    """分析单条视频的镜头边界。

    Args:
        path: 原始视频路径（可为中文，内部用代理读取）
        sample_interval_ms: 采样间隔（毫秒）
        progress_cb: 可选回调 (current_ms, duration_ms)

    Returns:
        {
          'ok': bool, 'error': str,
          'duration_ms': int, 'fps': float,
          'sample_count': int,
          'signals': [{'time_ms','hist','pixel','edge','luma','structure','combined'}, ...],
          'boundaries': [{'time_ms','reason','score','confidence'}, ...],  # 镜头切点
          'light_events': [{'time_ms','delta','kind'}],  # 灯光变化事件(非切镜)
          'shots': [{'start_ms','end_ms','index'}, ...],   # 由边界推导的候选镜头
        }
    """
    result = {
        "ok": False, "error": "", "duration_ms": 0, "fps": 0,
        "sample_count": 0, "signals": [], "boundaries": [],
        "light_events": [], "shots": [],
    }
    proxy = media.preview_link(path)
    cap = cv2.VideoCapture(proxy)
    if not cap.isOpened():
        result["error"] = "无法打开视频"
        return result

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_ms = int(total / fps * 1000) if fps else 0
    result["fps"] = fps
    result["duration_ms"] = duration_ms

    step_frames = max(1, int(fps * sample_interval_ms / 1000.0))
    samples = []  # (time_ms, hist, gray, luma)
    idx = 0
    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            break
        t_ms = int(idx / fps * 1000)
        gray = _gray_small(frame)
        luma = float(np.mean(gray))
        samples.append((t_ms, _hist_feature(frame), gray, luma))
        if progress_cb:
            progress_cb(t_ms, duration_ms)
        idx += step_frames
        if total and idx >= total:
            break
    cap.release()

    result["sample_count"] = len(samples)
    if len(samples) < 2:
        result["error"] = "采样帧不足，无法分析"
        return result

    # ---- 逐相邻样本计算多信号 ----
    signals = []
    for i in range(1, len(samples)):
        t1, h1, g1, l1 = samples[i - 1]
        t2, h2, g2, l2 = samples[i]

        hist_diff = float(cv2.compareHist(h1, h2, cv2.HISTCMP_BHATTACHARYYA))
        pixel_diff = float(np.mean(cv2.absdiff(g1, g2))) / 255.0

        e1, e2 = _edges(g1), _edges(g2)
        # 边缘结构差异：异或占比，反映画面结构是否变化
        edge_xor = float(np.mean(cv2.bitwise_xor(e1, e2) > 0))
        luma_delta = abs(l2 - l1) / 255.0

        # "结构信号" = 色彩 + 边缘；亮度单独统计
        structure = 0.6 * hist_diff + 0.4 * edge_xor
        # 综合分数：结构为主，像素为辅；亮度只给很小的权重
        combined = 0.55 * hist_diff + 0.25 * edge_xor + 0.15 * pixel_diff + 0.05 * luma_delta

        signals.append({
            "time_ms": t2,
            "hist": round(hist_diff, 4),
            "pixel": round(pixel_diff, 4),
            "edge": round(edge_xor, 4),
            "luma": round(luma_delta, 4),
            "structure": round(structure, 4),
            "combined": round(combined, 4),
        })
    result["signals"] = signals

    if len(signals) < 2:
        result["ok"] = True
        result["shots"] = [{"start_ms": 0, "end_ms": duration_ms, "index": 1}]
        return result

    # ---- 识别灯光变化事件（亮度突变但结构几乎不变） ----
    luma_arr = np.array([s["luma"] for s in signals])
    struct_arr = np.array([s["structure"] for s in signals])
    comb_arr = np.array([s["combined"] for s in signals])

    # ---- 自适应阈值 = 均值 + k*标准差 ----
    mean_c, std_c = float(np.mean(comb_arr)), float(np.std(comb_arr))
    threshold = mean_c + 1.0 * std_c
    threshold = max(threshold, 0.12)  # 保底阈值，避免全平视频被切碎

    # ---- 局部峰值检测 ----
    candidates = []
    for i, s in enumerate(signals):
        prev_v = signals[i - 1]["combined"] if i > 0 else -1
        next_v = signals[i + 1]["combined"] if i < len(signals) - 1 else -1
        is_peak = s["combined"] >= prev_v and s["combined"] >= next_v
        is_light_only = (s["luma"] > 0.10 and s["structure"] < 0.10)
        # 疑似灯光/色温变化：色彩(H)变化大，但边缘结构几乎不变，亮度也稳定
        # 三色温切换正是这种情形——不能当成确定的场景切换
        is_suspect_light = (s["hist"] > 0.14 and s["edge"] < 0.08 and s["luma"] < 0.12)
        if is_peak and s["combined"] >= threshold and not is_light_only:
            if is_suspect_light:
                conf = 0.35  # 低置信度，明确标记为待核验
                reason = "疑似灯光/色温变化(需人工核验是否同场景)"
                result["light_events"].append({
                    "time_ms": s["time_ms"], "delta": s["hist"], "kind": "疑似色温变化(作为候选边界保留)",
                })
            else:
                conf = min(0.99, 0.5 + (s["combined"] - threshold) / max(std_c, 1e-6) * 0.1)
                reason = _explain(s)
            candidates.append({
                "time_ms": s["time_ms"], "reason": reason,
                "score": s["combined"], "confidence": round(conf, 2),
            })
        elif s["luma"] > 0.12 and s["structure"] < 0.10:
            # 灯光变化：记录但不切镜
            result["light_events"].append({
                "time_ms": s["time_ms"], "delta": s["luma"], "kind": "亮度变化(未切镜)",
            })

    # ---- 合并过近边界（最小镜头 1.2 秒） ----
    min_gap_ms = 1200
    merged = []
    for c in candidates:
        if not merged or c["time_ms"] - merged[-1]["time_ms"] >= min_gap_ms:
            merged.append(c)
        else:
            # 保留分数更高的那个
            if c["score"] > merged[-1]["score"]:
                merged[-1] = c
    result["boundaries"] = merged

    # ---- 推导候选镜头 ----
    shots = []
    prev = 0
    for i, b in enumerate(merged):
        shots.append({"start_ms": prev, "end_ms": b["time_ms"], "index": len(shots) + 1})
        prev = b["time_ms"]
    shots.append({"start_ms": prev, "end_ms": duration_ms, "index": len(shots) + 1})
    # 过滤过短尾段（<0.6s）并入上一个
    shots = [s for s in shots if s["end_ms"] - s["start_ms"] >= 600 or len(shots) == 1]
    for i, s in enumerate(shots):
        s["index"] = i + 1
    result["shots"] = shots
    result["ok"] = True
    return result


def _explain(s):
    """给出可解释的边界原因。"""
    parts = []
    if s["hist"] > 0.18:
        parts.append("色彩分布明显变化")
    if s["edge"] > 0.15:
        parts.append("画面结构变化")
    if s["pixel"] > 0.20:
        parts.append("像素差异大")
    if not parts:
        parts.append("多信号综合超阈值")
    return "、".join(parts)
