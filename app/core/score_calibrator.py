# -*- coding: utf-8 -*-
"""用人评分校准自动质量分。

思路（对应「启发式不够懂内容好坏」）：
- OpenCV 启发式仍负责六维画面信号（清晰度/曝光/…）。
- 人工给片段打 0–100 分后，把「自动分 → 人工分」拟合为仿射校准
  calibrated ≈ a * auto_total + b。
- 样本够多时，再按六维分数学最小二乘权重，贴近人的偏好。
- 样本不足时不做假学习：直接返回原始启发式分，并标明未校准。

校准模型存项目 settings（score_calibration），可跨会话复用。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import numpy as np

from .quality_scorer import DIMENSIONS, _clamp

SETTINGS_KEY = "score_calibration"
MIN_AFFINE_SAMPLES = 3
MIN_WEIGHT_SAMPLES = 6


def _grade(total: float) -> str:
    if total >= 90:
        return "优秀"
    if total >= 80:
        return "良好"
    if total >= 70:
        return "可用"
    if total >= 60:
        return "需要人工检查"
    return "不推荐"


def collect_labeled_examples(clips: List[dict]) -> List[dict]:
    """从 clips 行里抽出「有人工分 + 有自动六维分」的样本。"""
    out = []
    for c in clips or []:
        hr = c.get("human_rating")
        if hr is None:
            continue
        try:
            human = int(hr)
        except (TypeError, ValueError):
            continue
        if human < 0 or human > 100:
            continue
        scores = None
        # 优先 quality_detail.scores；其次 score_text JSON
        detail_raw = c.get("quality_detail") or ""
        if detail_raw:
            try:
                detail = json.loads(detail_raw) if isinstance(detail_raw, str) else detail_raw
                scores = (detail or {}).get("scores")
            except Exception:
                scores = None
        if not scores:
            st = c.get("score_text") or ""
            if st:
                try:
                    parsed = json.loads(st) if isinstance(st, str) else st
                    scores = (parsed or {}).get("scores")
                except Exception:
                    scores = None
        if not isinstance(scores, dict):
            continue
        vec = []
        ok = True
        for d in DIMENSIONS:
            if d not in scores:
                ok = False
                break
            try:
                vec.append(float(scores[d]))
            except (TypeError, ValueError):
                ok = False
                break
        if not ok:
            continue
        auto_total = c.get("quality_raw_total")
        if auto_total is None:
            auto_total = c.get("quality_total")
        try:
            auto_total = float(auto_total)
        except (TypeError, ValueError):
            # 用默认权重重算
            from .quality_scorer import DEFAULT_WEIGHTS
            auto_total = sum(scores[d] * DEFAULT_WEIGHTS[d] for d in DIMENSIONS)
        out.append({
            "clip_id": c.get("id"),
            "human": human,
            "auto_total": auto_total,
            "scores": {d: vec[i] for i, d in enumerate(DIMENSIONS)},
            "vec": vec,
        })
    return out


def fit_calibration(examples: List[dict]) -> Dict[str, Any]:
    """根据人工标签拟合校准模型。"""
    model: Dict[str, Any] = {
        "ok": False,
        "mode": "none",
        "n_samples": len(examples),
        "a": 1.0,
        "b": 0.0,
        "weights": None,
        "bias": 0.0,
        "mae": None,
        "message": "样本不足，仍使用原始启发式分",
    }
    if len(examples) < MIN_AFFINE_SAMPLES:
        return model

    autos = np.array([e["auto_total"] for e in examples], dtype=float)
    humans = np.array([e["human"] for e in examples], dtype=float)

    # 仿射：human ≈ a * auto + b
    A = np.column_stack([autos, np.ones(len(autos))])
    coef, _, _, _ = np.linalg.lstsq(A, humans, rcond=None)
    a, b = float(coef[0]), float(coef[1])
    # 防止极端斜率
    if not np.isfinite(a) or abs(a) < 1e-6:
        a, b = 1.0, float(np.mean(humans - autos))
    pred = a * autos + b
    mae = float(np.mean(np.abs(pred - humans)))

    model.update({
        "ok": True,
        "mode": "affine",
        "a": round(a, 6),
        "b": round(b, 6),
        "mae": round(mae, 3),
        "message": f"仿射校准（{len(examples)} 条人工分）：score' = {a:.3f}*auto + {b:.1f}",
    })

    # 样本够：六维最小二乘权重
    if len(examples) >= MIN_WEIGHT_SAMPLES:
        X = np.array([e["vec"] for e in examples], dtype=float)
        Xb = np.column_stack([X, np.ones(len(X))])
        w, _, _, _ = np.linalg.lstsq(Xb, humans, rcond=None)
        weights = {d: round(float(w[i]), 6) for i, d in enumerate(DIMENSIONS)}
        bias = float(w[-1])
        pred_w = Xb @ w
        mae_w = float(np.mean(np.abs(pred_w - humans)))
        # 仅当维度模型不比仿射差太多时启用
        if mae_w <= mae * 1.15 + 1.0:
            model.update({
                "mode": "weighted",
                "weights": weights,
                "bias": round(bias, 6),
                "mae": round(mae_w, 3),
                "message": (
                    f"六维权重校准（{len(examples)} 条人工分），"
                    f"MAE={mae_w:.1f}"
                ),
            })
    return model


def apply_calibration(score_result: dict, model: Optional[dict]) -> dict:
    """把校准应用到 quality_scorer 的结果（原地增强后返回）。"""
    if not score_result.get("ok"):
        return score_result
    raw_total = float(score_result.get("total", 0))
    score_result["raw_total"] = round(raw_total)
    score_result["calibrated"] = False
    score_result["calibration_meta"] = {"mode": "none"}

    if not model or not model.get("ok"):
        score_result["disclaimer"] = (
            score_result.get("disclaimer", "")
            + "｜尚未用人评分校准（样本不足或未标注）"
        )
        return score_result

    cal = raw_total
    mode = model.get("mode")
    if mode == "weighted" and model.get("weights"):
        scores = score_result.get("scores") or {}
        cal = float(model.get("bias", 0.0))
        for d in DIMENSIONS:
            cal += float(model["weights"].get(d, 0.0)) * float(scores.get(d, 0))
    elif mode == "affine":
        cal = float(model.get("a", 1.0)) * raw_total + float(model.get("b", 0.0))

    cal = _clamp(cal)
    score_result["total"] = round(cal)
    score_result["grade"] = _grade(cal)
    score_result["calibrated"] = True
    score_result["calibration_meta"] = {
        "mode": mode,
        "n_samples": model.get("n_samples"),
        "mae": model.get("mae"),
        "message": model.get("message"),
        "raw_total": round(raw_total),
        "calibrated_total": round(cal),
    }
    score_result["disclaimer"] = (
        "图像信号启发式 + 人工评分校准；"
        f"{model.get('message', '')}"
    )
    return score_result


def rebuild_from_clips(clips: List[dict]) -> Dict[str, Any]:
    """从项目全部 clips 重建校准模型。"""
    return fit_calibration(collect_labeled_examples(clips))


def dumps(model: dict) -> str:
    return json.dumps(model, ensure_ascii=False)


def loads(raw: str) -> Optional[dict]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None
