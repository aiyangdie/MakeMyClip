# -*- coding: utf-8 -*-
"""候选片段质量评分（阶段三）。

原则（对应任务书）：
- 多维度独立评分，每项 0-100，保留全部明细，不只有一个总分。
- 分数是"可解释的图像信号估计"，不是"经过验证的 AI 准确率"——如实标注。
- 评分只用于推荐排序，绝不自动删除原始素材。
- 内容准确性优先于画面美观：这一层只评"画面质量"，内容是否对由 matcher 判断。

维度（每项都有明确的图像依据）：
- sharpness 清晰度：拉普拉斯方差（对焦程度）
- exposure  曝光：亮度均值与过曝/欠曝像素占比
- stability 稳定性：相邻采样帧的整体位移/差异
- composition 构图：主体占比是否合理、边缘分布
- cleanliness 画面干净度：背景杂乱度（边缘密度反向）
- occlusion  遮挡：前景/肤色占比（占比高说明可能被手挡住）
"""
import cv2
import numpy as np

from .. import media


DIMENSIONS = ["sharpness", "exposure", "stability", "composition", "cleanliness", "occlusion"]
DIM_NAMES = {
    "sharpness": "清晰度", "exposure": "曝光", "stability": "稳定性",
    "composition": "构图", "cleanliness": "画面干净度", "occlusion": "无遮挡",
}
# 默认权重（无人评分校准时使用）；校准时可由 score_calibrator 替换加权方式
DEFAULT_WEIGHTS = {
    "sharpness": 0.28, "exposure": 0.22, "stability": 0.20,
    "composition": 0.15, "cleanliness": 0.10, "occlusion": 0.05,
}


def _clamp(x):
    return max(0.0, min(100.0, x))


def _sample(path, start_ms, end_ms, interval_ms=300, max_n=24):
    proxy = media.preview_link(path)
    cap = cv2.VideoCapture(proxy)
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    sf = max(0, int(start_ms / 1000 * fps))
    ef = max(sf + 1, int(end_ms / 1000 * fps))
    step = max(1, int(fps * interval_ms / 1000))
    if (ef - sf) // step > max_n:
        step = max(step, (ef - sf) // max_n)
    out = []
    idx = sf
    while idx < ef:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, fr = cap.read()
        if not ok:
            break
        out.append(fr)
        idx += step
    cap.release()
    return out


def score_segment(path, start_ms, end_ms, calibration=None):
    """给单个候选片段打分，返回：
    {
      'ok':bool, 'error':str,
      'scores': {dim: 0-100}, 'total': 0-100, 'grade': 等级,
      'detail': {dim: 依据说明}, 'metrics': {...},
      'disclaimer': 说明这是图像信号估计，非验证过的AI准确率,
      'raw_total': 启发式原始总分（校准前）,
      'calibrated': 是否已用人评分校准,
    }

    calibration: 可选，score_calibrator.fit_calibration 产出的模型；
    有足够人工标签时会把 total 调成更贴近人的偏好。
    """
    res = {
        "ok": False, "error": "", "scores": {}, "total": 0,
        "grade": "", "detail": {}, "metrics": {},
        "disclaimer": "图像信号启发式估计，仅用于排序参考，非经验证的AI准确率",
        "raw_total": 0, "calibrated": False,
    }
    frames = _sample(path, start_ms, end_ms)
    if len(frames) < 2:
        res["error"] = "有效帧不足，无法评分"
        return res

    sharp_list, bright_list, over_list, under_list = [], [], [], []
    skin_list, edge_list, gray_prev, motion_list = [], [], None, []
    for fr in frames:
        small = cv2.resize(fr, (240, 135))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        # 清晰度：拉普拉斯方差
        sharp_list.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
        # 曝光
        bright_list.append(float(np.mean(gray)) / 255.0)
        over_list.append(float(np.mean(gray > 245)))
        under_list.append(float(np.mean(gray < 15)))
        # 遮挡弱信号：肤色占比
        ycrcb = cv2.cvtColor(small, cv2.COLOR_BGR2YCrCb)
        skin = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
        skin_list.append(float(np.count_nonzero(skin)) / skin.size)
        # 边缘密度
        edges = cv2.Canny(gray, 50, 150)
        edge_list.append(float(np.count_nonzero(edges)) / edges.size)
        # 稳定性：相邻帧差
        if gray_prev is not None:
            motion_list.append(float(np.mean(cv2.absdiff(gray_prev, gray))) / 255.0)
        gray_prev = gray

    ma = lambda a: float(np.mean(a))
    sharp = ma(sharp_list)
    bright = ma(bright_list)
    over = ma(over_list)
    under = ma(under_list)
    skin = ma(skin_list)
    edge = ma(edge_list)
    motion = ma(motion_list) if motion_list else 0.0

    # ---- 各项打分（分段映射，可解释）----
    # 清晰度：拉普拉斯方差 100 以上视为很清晰
    s_sharp = _clamp(sharp / 100.0 * 100)
    # 曝光：亮度适中 0.55 最佳，偏离扣分；过曝/欠曝占比直接罚分
    bright_score = 100 - abs(bright - 0.55) * 220
    s_exposure = _clamp(bright_score - over * 300 - under * 300)
    # 稳定性：帧差越小越稳（商品展示常有手部操作，容忍度放宽）
    s_stability = _clamp(100 - motion * 400)
    # 构图：边缘适中最理想（太低=空/糊，太高=杂乱），主体不贴边
    s_composition = _clamp(100 - abs(edge - 0.09) * 500)
    # 干净度：边缘密度低更干净
    s_clean = _clamp(100 - max(0, edge - 0.05) * 700)
    # 无遮挡：肤色/前景占比越低越好。
    # 注意：暖色木质家具会被肤色阈值大面积误检，家具场景下该维度不可靠，
    # 只做弱参考——对超出 0.35 基线的部分才罚分，避免错杀正常木质镜头。
    s_occlusion = _clamp(100 - max(0, skin - 0.35) * 160)

    scores = {
        "sharpness": round(s_sharp), "exposure": round(s_exposure),
        "stability": round(s_stability), "composition": round(s_composition),
        "cleanliness": round(s_clean), "occlusion": round(s_occlusion),
    }
    # 总分：清晰度/曝光/稳定性权重高一些（默认权重；校准可在其后改写 total）
    weights = DEFAULT_WEIGHTS
    total = round(sum(scores[d] * weights[d] for d in DIMENSIONS))

    if total >= 90:
        grade = "优秀"
    elif total >= 80:
        grade = "良好"
    elif total >= 70:
        grade = "可用"
    elif total >= 60:
        grade = "需要人工检查"
    else:
        grade = "不推荐"

    detail = {
        "sharpness": f"拉普拉斯方差 {sharp:.1f}（越高越清晰）",
        "exposure": f"平均亮度 {bright:.2f}，过曝占比 {over:.3f}，欠曝占比 {under:.3f}",
        "stability": f"相邻帧平均差异 {motion:.4f}（越小越稳）",
        "composition": f"边缘密度 {edge:.4f}（适中为佳，过高可能杂乱）",
        "cleanliness": f"边缘密度 {edge:.4f}（越低画面越干净）",
        "occlusion": f"肤色前景占比 {skin:.3f}（弱参考：偏高可能被手遮挡，但暖色木质会大面积误检，权重已降低）",
    }
    res["ok"] = True
    res["scores"] = scores
    res["total"] = total
    res["raw_total"] = total
    res["grade"] = grade
    res["detail"] = detail
    res["metrics"] = {
        "sharpness_var": round(sharp, 2), "brightness": round(bright, 3),
        "over_ratio": round(over, 4), "under_ratio": round(under, 4),
        "motion_mean": round(motion, 4), "edge_density": round(edge, 4),
        "skin_ratio": round(skin, 4), "sample_frames": len(frames),
    }
    if calibration:
        from . import score_calibrator
        return score_calibrator.apply_calibration(res, calibration)
    return res


def format_scores(score_result):
    """把评分结果格式化成一行可读文本，用于界面/数据库。"""
    if not score_result.get("ok"):
        return f"评分失败：{score_result.get('error','')}"
    s = score_result["scores"]
    parts = [f"{DIM_NAMES[k]}{s[k]}" for k in DIMENSIONS]
    line = f"总分{score_result['total']}({score_result['grade']})｜" + " ".join(parts)
    if score_result.get("calibrated") and score_result.get("raw_total") is not None:
        line += f"｜校准前{score_result['raw_total']}"
    return line
