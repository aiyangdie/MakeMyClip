# -*- coding: utf-8 -*-
"""分镜匹配引擎（阶段三）。

严格按任务书的选片五步法：
1. 先排除不合格片段（质量过低、无法解码、视觉证据与目标冲突）。
2. 再比较清晰度/稳定性/曝光/构图/动作完整度（用质量分）。
3. 检查与已选镜头的重复程度（同一素材、同一镜头、相似 cue 组合）。
4. 考虑时长与节奏（片段时长落在合理区间加分）。
5. 给出最佳候选 + 备选列表 + 推荐理由 + 置信度。

铁律：
- 内容准确性优先于画面美观：视觉证据不匹配的，画面再好也不选。
- 视觉证据不足时一律标"需人工核验"，置信度压低，绝不自动确认语义。
- 无合格候选：返回"缺少素材，暂不展示" + 补拍建议，不用别的镜头冒充。
- 已锁定的分镜：跳过，保持原选片不变。
- 分镜规则来自外部 JSON 模板，不写死在代码里。
"""
import json
from pathlib import Path

from .. import config


DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent.parent / "templates" / "furniture" / "nightstand.json"


def load_template(path=None):
    p = Path(path) if path else DEFAULT_TEMPLATE
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _cues_of(clip):
    """从片段记录中解析视觉 cue 代码集合。

    clip 需带 vision_labels（JSON 字符串或 list）字段。
    """
    labels = clip.get("vision_labels")
    if isinstance(labels, str):
        try:
            labels = json.loads(labels or "[]")
        except Exception:
            labels = []
    labels = labels or []
    return {l.get("code") for l in labels if isinstance(l, dict)}


def _parse_quality(clip):
    # 有人工评分时直接用人分（标签优先）；否则用校准后的自动分 quality_total
    hr = clip.get("human_rating")
    if hr is not None:
        try:
            return int(hr)
        except (TypeError, ValueError):
            pass
    sj = clip.get("score_text") or ""  # 兼容：质量明细存 score_text
    total = clip.get("quality_total")
    if total is None:
        # 从 "总分89(良好)|..." 中解析
        import re
        m = re.search(r"总分(\d+)", sj)
        total = int(m.group(1)) if m else 0
    return int(total or 0)


def _duration_ok(clip, lo=1.5, hi=12.0):
    dur = (clip.get("end_ms", 0) - clip.get("start_ms", 0)) / 1000.0
    return lo <= dur <= hi


def _dedup_penalty(clip, used):
    """与已选镜头的重复惩罚：同素材高罚，cue 组合雷同中罚。"""
    penalty = 0
    cues = _cues_of(clip)
    for u in used:
        if u.get("asset_id") == clip.get("asset_id"):
            penalty += 30                      # 同一原始素材已被用过
        if cues and cues & set(u.get("cues", [])) and len(cues & set(u.get("cues", []))) >= 2:
            penalty += 12                      # 视觉线索组合雷同
    return min(60, penalty)


def match_one(sb, clips, used, tpl):
    """为单个分镜挑选候选。sb/clips 均为 dict。"""
    name = sb.get("name", "")
    # 取该分镜的 required_cues：优先模板精确定义，否则用别名表推断
    rule = next((r for r in tpl.get("storyboards", []) if r["name"] == name), None)
    required = set(rule.get("required_cues", [])) if rule else set()
    if not required:
        for alias, cues in tpl.get("cue_aliases", {}).items():
            if alias in name:
                required = set(cues)
                break
    if not required:
        # 没有明确的内容证据要求时，宁可报缺失，也不强行用别的镜头凑数。
        # 这对应任务书铁律："某卖点没有真实画面时，显示缺失状态，不用其他镜头冒充。"
        return {
            "status": "未找到合适素材",
            "best": None, "candidates": [],
            "reason": "分镜模板未定义可识别的内容证据，无法自动匹配（避免强行凑镜头）",
            "confidence": 0, "need_review": True,
            "missing": True,
            "advice": "请在该商品的 JSON 分镜模板中，为此分镜补充 required_cues 定义。",
        }

    min_q = rule.get("min_quality", 50) if rule else 50
    advice = (rule.get("advice") if rule else "") or "补拍：按分镜展示目标拍摄稳定清晰的画面。"

    scored = []
    for c in clips:
        q = _parse_quality(c)
        cues = _cues_of(c)
        hit = required & cues
        # 第一步：质量硬门槛
        if q < min_q:
            continue
        # 内容匹配：命中 required cue 才进入候选（内容准确性优先）
        if not hit:
            continue
        # 时长适配
        dur_bonus = 8 if _duration_ok(c) else 0
        dedup = _dedup_penalty(c, used)
        content = len(hit) / len(required)     # 内容匹配度 0..1
        # 总分：内容 60% + 质量 40%，再扣重复、加时长
        final = content * 60 + (q / 100.0) * 40 - dedup + dur_bonus
        final = max(0, round(final, 1))

        # 置信度由内容证据决定；视觉是启发式的，上限压到 0.75，需核验
        conf = round(min(0.75, 0.35 + content * 0.4), 2)
        need_review = True
        reasons = [
            f"画面质量总分{q}",
            f"视觉证据命中 {','.join(sorted(hit))}",
        ]
        if dedup:
            reasons.append(f"与已选镜头重复度扣分{dedup}")
        if q < 60:
            reasons.append("质量偏低，建议人工看画面")
        reasons.append("本地视觉为启发式识别，语义需人工核验")

        scored.append({
            "clip": c, "score": final, "confidence": conf,
            "need_review": need_review, "reason": "；".join(reasons),
            "cues": list(cues),
        })

    scored.sort(key=lambda x: (-x["score"], -x["confidence"]))
    if not scored:
        return {
            "status": "未找到合适素材",
            "best": None, "candidates": [],
            "reason": "没有片段同时满足质量门槛与内容证据要求",
            "confidence": 0, "need_review": True,
            "missing": True, "advice": advice,
        }

    best = scored[0]
    return {
        "status": "候选待核验",
        "best": best, "candidates": scored[:5],
        "reason": best["reason"], "confidence": best["confidence"],
        "need_review": True, "missing": False, "advice": "",
    }


def match_all(storyboards, clips, template_path=None):
    """对所有分镜匹配。返回 {sb_id: result}。

    锁定或已确认的分镜跳过匹配，保持原状（非破坏性编辑铁律）。
    """
    tpl = load_template(template_path) or {"storyboards": [], "cue_aliases": {}}
    results = {}
    used = []
    for sb in storyboards:
        # 键统一用字符串：与 JSON 持久化、界面按 str(id) 读取保持一致
        key = str(sb["id"])
        if sb.get("locked") or sb.get("status") == "已确认":
            results[key] = {
                "status": sb.get("status", "已确认"), "skipped": True,
                "reason": "镜头已锁定或已确认，自动匹配未覆盖",
                "best": None, "candidates": [], "confidence": 1.0,
                "need_review": False, "missing": False, "advice": "",
            }
            continue
        res = match_one(sb, clips, used, tpl)
        results[key] = res
        if res["best"]:
            used.append({
                "asset_id": res["best"]["clip"].get("asset_id"),
                "cues": res["best"]["cues"],
            })
    return results


def format_result(res):
    """把匹配结果转成一行可读文本。"""
    if res.get("skipped"):
        return f'[{res["status"]}] 自动匹配已跳过：{res["reason"]}'
    if res.get("missing"):
        return f'[缺少素材，暂不展示] {res["reason"]}｜补拍建议：{res["advice"]}'
    b = res["best"]
    if not b:
        return "无结果"
    c = b["clip"]
    return (f'[候选待核验] 最佳：{c.get("filename", "?")} '
            f'{c.get("start_ms",0)/1000:.1f}-{c.get("end_ms",0)/1000:.1f}s '
            f'评分{b["score"]} 置信{b["confidence"]}｜{res["reason"]}')
