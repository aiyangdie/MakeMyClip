# -*- coding: utf-8 -*-
"""阶段 B · 项目读取桥接（ProjectDB → 视图模型）

铁律：
  - **只读**。本模块所有 db 调用都必须是 get_* / load_*，绝不 add/update/delete。
  - 复用既有能力：分组用 wizard_lines.group_of()，不自己重写一套。
  - 五态派生规则集中在此，UI 不得再判断状态。

五态派生依据（真实数据验证过）：
  assets.analysis_status 实际取值：'已分析'(27) / '未分析'(18)
  clips.verify_state 实际取值：'待核验'(49)
  → 已分析 + 有'待核验'clip  = 待人工确认
  → 已分析 + 无待核验       = 已完成基础测量
"""
from collections import Counter
from pathlib import Path
from typing import List, Optional

from . import models as M
from .image_support import is_image

# 复用旧程序的既有逻辑（只读引用，不改它）
from ..core import wizard_lines as wl


def _analyzer_kind(analysis_status: str) -> str:
    """判定这条素材的分析来源。

    当前产品只有 OpenCV 启发式一种实现（已由代码盘点确认：
    app/ai/vision_provider.py 的 provider_factory 只注册 HeuristicVisionProvider，
    全 app/ 零网络调用）。
    所以"已分析"一律归为 heuristic —— 绝不写成 vlm/cloud。

    将来接入模型后，改为从 analysis_runs.analyzer_kind 读取即可，
    本函数是唯一需要改的地方。
    """
    if analysis_status in ("已分析", "已找到候选", "候选待核验"):
        return "heuristic"
    return ""


def _derive_status(asset_row: dict, pending: int) -> str:
    """五态派生。"""
    raw = (asset_row.get("analysis_status") or "").strip()
    decode_ok = asset_row.get("decode_ok", 1)

    if raw in ("分析失败",) or (raw == "" and decode_ok == 0):
        return M.ST_FAILED
    if raw == "未分析" or raw == "":
        # decode 失败且未分析 → 仍算失败（用户需要知道这条读不了）
        return M.ST_FAILED if decode_ok == 0 else M.ST_UNANALYZED
    if pending > 0:
        return M.ST_CONFIRM
    return M.ST_MEASURED


def _note_for(status: str, pending: int, is_img: bool, analyzer: str, error: str) -> str:
    """给用户看的一句话说明（必须诚实）。"""
    if status == M.ST_FAILED:
        return f"读取失败：{error or '文件可能已损坏或格式不支持'}"
    if status == M.ST_UNANALYZED:
        return "还没分析，点「开始分析」后才会处理"
    if status == M.ST_CONFIRM:
        return f"有 {pending} 处需你确认后才能进剪辑方案"
    if status == M.ST_MEASURED:
        if analyzer == "heuristic":
            return "已完成基础测量（画面变化/亮度/清晰度），尚未接入识别模型"
        return "已完成分析"
    return ""


def load_assets(db) -> List[M.AssetVM]:
    """读全部素材并转成视图模型（只读）。"""
    assets = db.get_assets() or []
    # 一次读全部 clips，统计每素材的待核验数量（避免 N+1 查询）
    clips = db.get_clips() or []
    pending_by_asset = Counter()
    for c in clips:
        if (c.get("verify_state") or "") == "待核验":
            aid = c.get("asset_id")
            if aid is not None:
                pending_by_asset[aid] += 1

    # 用户自定义分组覆盖（复用旧逻辑同一份 settings key）
    try:
        overrides = wl.load_custom_groups(db)
    except Exception:  # noqa: BLE001 - 分组读失败不该让整页崩
        overrides = {}

    out: List[M.AssetVM] = []
    for a in assets:
        aid = a.get("id")
        img = is_image(a.get("path") or "")
        pend = pending_by_asset.get(aid, 0)
        status = _derive_status(a, pend)
        analyzer = _analyzer_kind(a.get("analysis_status") or "")
        try:
            grp = wl.group_of(a, overrides)
        except Exception:  # noqa: BLE001
            grp = "未分组"
        out.append(M.AssetVM(
            asset_id=aid,
            path=a.get("path") or "",
            filename=a.get("filename") or Path(a.get("path") or "").name,
            is_image=img,
            duration_ms=int(a.get("duration_ms") or 0),
            width=int(a.get("width") or 0),
            height=int(a.get("height") or 0),
            fps=float(a.get("fps") or 0),
            thumb_path=a.get("thumb_path") or "",
            group=grp,
            status=status,
            status_label=M.STATUS_LABEL[status],
            status_tone=M.STATUS_TONE[status],
            pending_count=pend,
            shot_count=int(a.get("shot_count") or 0),
            decode_ok=bool(a.get("decode_ok", 1)),
            error=(a.get("error") or "").strip(),
            analyzer_kind=analyzer,
            analyzer_label=M.ANALYZER_LABEL.get(analyzer, "未分析"),
            note=_note_for(status, pend, img, analyzer, (a.get("error") or "").strip()),
        ))
    return out


def build_stats(assets: List[M.AssetVM]) -> M.AssetStats:
    st = M.AssetStats(total=len(assets))
    for a in assets:
        if a.status == M.ST_UNANALYZED:
            st.unanalyzed += 1
        elif a.status == M.ST_ANALYZING:
            st.analyzing += 1
        elif a.status == M.ST_MEASURED:
            st.measured += 1
        elif a.status == M.ST_CONFIRM:
            st.confirm += 1
        elif a.status == M.ST_FAILED:
            st.failed += 1
        if a.is_image:
            st.images += 1
        else:
            st.videos += 1
    return st


def build_groups(assets: List[M.AssetVM], extra=None) -> List[M.GroupVM]:
    """分组统计（含"全部"）。复用 sort 规则：数量降序、名称升序。"""
    c = Counter(a.group for a in assets)
    for name in (extra or []):
        c.setdefault(name, 0)
    rows = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
    return [M.GroupVM("全部", len(assets))] + [M.GroupVM(k, v) for k, v in rows]


def load_project(db, db_path=None) -> M.ProjectVM:
    """读一个项目的完整视图（只读）。"""
    assets = load_assets(db)
    warnings = []

    # 解析失败 / 损坏素材要显式提示，不能静默
    bad = [a for a in assets if a.status == M.ST_FAILED]
    if bad:
        warnings.append(f"有 {len(bad)} 条素材读取失败，无法参与剪辑")

    try:
        meta = db.get_meta() or {}
    except Exception:  # noqa: BLE001
        meta = {}
    try:
        product = db.get_product_info() or {}
    except Exception:  # noqa: BLE001
        product = {}
    try:
        tl = db.get_timeline() or []
    except Exception:  # noqa: BLE001
        tl = []
    try:
        sbs = db.get_storyboards() or []
    except Exception:  # noqa: BLE001
        sbs = []

    return M.ProjectVM(
        db_path=str(db_path or getattr(db, "db_path", "")),
        name=meta.get("name") or "未命名项目",
        assets=assets,
        groups=build_groups(assets),
        stats=build_stats(assets),
        product_info=product,
        timeline_count=len(tl),
        storyboard_count=len(sbs),
        warnings=warnings,
    )


# ============================================================================
# 剪辑方案页的读取（阶段 C 才上界面，这里先给只读契约，便于测试与将来复用）
# ============================================================================
def load_segments(db) -> List[M.SegmentVM]:
    """读时间线 → 镜头视图（只读）。"""
    try:
        shots = db.get_timeline() or []
    except Exception:  # noqa: BLE001
        return []
    try:
        lines = {str(l.get("shot_id")): (l.get("text") or "")
                 for l in (db.get_narration_lines() or [])}
    except Exception:  # noqa: BLE001
        lines = {}

    out = []
    for s in shots:
        sid = str(s.get("shot_id") or "")
        has_asset = bool((s.get("asset_path") or "").strip())
        if not has_asset:
            raw = s.get("sub_segments") or ""
            has_asset = bool(raw.strip()) if isinstance(raw, str) else bool(raw)
        out.append(M.SegmentVM(
            shot_id=sid,
            seq=int(s.get("seq") or 0),
            name=s.get("name") or "未命名镜头",
            asset_path=s.get("asset_path") or "",
            start_ms=int(s.get("start_ms") or 0),
            end_ms=int(s.get("end_ms") or 0),
            duration_ms=int(s.get("duration_ms") or 0),
            target_ms=int(s.get("target_ms") or 0),
            locked=bool(s.get("locked")),
            thumb_path=s.get("thumb_path") or "",
            subtitle=lines.get(sid, ""),
            # 当前没有真实识别结果：L1/L2 一律空，l2_confirmed 一律 None
            # 绝不伪造标签（任务书：没有真实识别结果时不得伪造标签）
            l1=[],
            l2="",
            l2_confirmed=None,
            action_source="heuristic" if has_asset else "none",
            has_asset=has_asset,
        ))
    return out


def ai_capability_summary(db) -> dict:
    """如实汇报当前 AI 能力边界（供界面"能力说明"处显示）。"""
    runs = 0
    try:
        conn = db.connect()
        with conn as c:
            try:
                runs = c.execute("SELECT COUNT(*) n FROM analysis_runs").fetchone()["n"]
            except Exception:
                runs = 0
    except Exception:  # noqa: BLE001
        runs = 0
    return {
        "has_vlm": False,          # 代码盘点结论：app/ 内无任何模型调用
        "has_cloud": False,
        "analyzer_in_use": "heuristic",
        "note": "当前仅 OpenCV 基础算法测量（画面变化/亮度/清晰度），"
                "未接入视觉或语言模型，无法理解商品动作语义。",
        "analysis_runs": runs,
    }
