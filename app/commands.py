# -*- coding: utf-8 -*-
"""智能体操作层（阶段八新增，不影响任何已有功能）。

作用：把程序的剪辑能力"翻译"成智能体能安全调用的命令。
护栏（焊死在代码里，任何智能体都绕不过）：
1. 原始素材只读——本层没有任何写素材的入口。
2. 锁定镜头拒绝修改——由 db.update_shot 在数据库层强制执行，本层如实报错。
3. 导出成片必须带 confirm=True（代表用户已明确点头），否则拒绝。
4. 每一条命令（成功/失败/被拒绝）都追加写入 logs/agent_ops.log，可审计可回查。
5. 本层只新增文件，不改界面、不改核心渲染/数据库代码——界面与智能体走同一底座。

单位约定：对外接口统一用"秒"（人类好理解），数据库内部仍是毫秒。
"""
import json
import time
from pathlib import Path

from . import config, media
from . import db as dbmod
from .core import video_editor


class CommandError(Exception):
    """命令执行失败/被护栏拒绝。message 会原样转给智能体。"""


# ---------------- 日志（审计） ----------------

AGENT_LOG = config.LOG_DIR / "agent_ops.log"


def _log(action, detail="", ok=True, project=""):
    """追加一行 JSON 日志。只追加，不覆盖（append-only）。"""
    try:
        AGENT_LOG.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "action": action,
               "ok": bool(ok), "project": str(project), "detail": str(detail)[:500]}
        with AGENT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 日志失败不阻断命令本身


def read_log(tail=30):
    """读取最近 tail 条智能体操作日志（审计用）。"""
    if not AGENT_LOG.exists():
        return []
    lines = AGENT_LOG.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for ln in lines[-int(tail):]:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


# ---------------- 项目定位 ----------------

def list_projects():
    """列出 projects/ 目录下全部项目（名称、文件、大小、最后修改时间）。"""
    out = []
    for p in sorted(config.DB_DIR.glob("*.db")):
        st = p.stat()
        out.append({"name": p.stem, "file": str(p),
                    "size_mb": round(st.st_size / 1048576, 2),
                    "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))})
    return out


def _resolve_project(project) -> Path:
    """project 可以是项目名、文件名或完整路径。只允许打开存在的 .db 文件。"""
    project = str(project).strip()
    cand = Path(project)
    if not cand.suffix:
        cand = cand.with_suffix(".db")
    if cand.is_absolute():
        if cand.exists():
            return cand
    else:
        p = config.DB_DIR / cand
        if p.exists():
            return p
    raise CommandError(f"找不到项目「{project}」。请先用 list_projects 查看现有项目。")


def _open(project):
    return dbmod.ProjectDB(str(_resolve_project(project)))


# ---------------- 只读查询 ----------------

def list_shots(project):
    """列出项目时间线的全部镜头（含缺镜头），只读。"""
    db = _open(project)
    rows = []
    for s in db.get_timeline():
        subs = []
        try:
            subs = json.loads(s.get("sub_segments") or "[]") or []
        except json.JSONDecodeError:
            subs = []
        rows.append({
            "shot_id": s["shot_id"], "seq": s.get("seq"),
            "name": s.get("name"),
            "asset": Path(s.get("asset_path", "")).name if s.get("asset_path") else "",
            "start_s": round((s.get("start_ms", 0) or 0) / 1000, 2),
            "end_s": round((s.get("end_ms", 0) or 0) / 1000, 2),
            "target_s": round((s.get("target_ms", 0) or 0) / 1000, 2),
            "locked": bool(s.get("locked")),
            "linked": bool(subs), "linked_parts": len(subs),
            "cached": bool(s.get("cache_key")),
        })
    _log("list_shots", f"{len(rows)}个镜头", project=project)
    return rows


def get_shot(project, shot_id):
    """查看单个镜头详情（含素材时长，便于判断能取多少画面）。只读。"""
    db = _open(project)
    s = db.get_shot(shot_id)
    if not s:
        raise CommandError(f"镜头 {shot_id} 不存在。")
    info = {"shot_id": s["shot_id"], "seq": s.get("seq"), "name": s.get("name"),
            "asset_path": s.get("asset_path", ""),
            "start_s": round((s.get("start_ms", 0) or 0) / 1000, 2),
            "end_s": round((s.get("end_ms", 0) or 0) / 1000, 2),
            "target_s": round((s.get("target_ms", 0) or 0) / 1000, 2),
            "locked": bool(s.get("locked")),
            "sub_segments": s.get("sub_segments", ""),
            "cache_key": s.get("cache_key", "")}
    if s.get("asset_path") and Path(s["asset_path"]).exists():
        p = media.probe(s["asset_path"])
        info["asset_duration_s"] = round(p.get("duration_ms", 0) / 1000, 2)
    _log("get_shot", f"镜头{shot_id}", project=project)
    return info


def list_assets(project):
    """列出项目已导入的全部素材。只读。"""
    db = _open(project)
    rows = []
    for a in db.get_assets():
        rows.append({"asset_id": a.get("id"), "path": a.get("path", ""),
                     "name": Path(a.get("path", "")).name,
                     "duration_s": round((a.get("duration_ms", 0) or 0) / 1000, 2)})
    _log("list_assets", f"{len(rows)}条素材", project=project)
    return rows


# ---------------- 单镜头修改（非破坏性：只动这一行） ----------------

def set_shot_time(project, shot_id, start_s, end_s):
    """修改单个镜头的起止时间（秒）。只影响该镜头；锁定镜头拒绝。"""
    db = _open(project)
    start_s, end_s = float(start_s), float(end_s)
    if end_s <= start_s:
        raise CommandError("结束时间必须大于开始时间。")
    s = db.get_shot(shot_id)
    if not s:
        raise CommandError(f"镜头 {shot_id} 不存在。")
    dur = (s.get("end_ms", 0) - s.get("start_ms", 0)) or 0
    ok = db.update_shot(shot_id, start_ms=int(start_s * 1000), end_ms=int(end_s * 1000))
    if not ok:
        _log("set_shot_time", f"镜头{shot_id}被拒绝(锁定)", ok=False, project=project)
        raise CommandError(f"镜头「{s.get('name')}」已锁定，拒绝修改。请用户先在界面解锁。")
    db.update_shot(shot_id, cache_key="")  # 清缓存标识=只让这一个镜头重渲染
    _log("set_shot_time", f"镜头{shot_id}: {start_s}-{end_s}s", project=project)
    return {"ok": True, "shot_id": shot_id, "start_s": start_s, "end_s": end_s,
            "note": "仅此镜头已改，其它镜头未动。"}


def set_shot_target(project, shot_id, target_s):
    """设置单个镜头的建议时长（秒，0=不限，用素材原长）。短则末帧定格补足，长则截短。"""
    db = _open(project)
    target_s = max(0.0, float(target_s))
    s = db.get_shot(shot_id)
    if not s:
        raise CommandError(f"镜头 {shot_id} 不存在。")
    if target_s > 0 and target_s < 1.0:
        raise CommandError("建议时长最短 1 秒（太短观众看不清）。")
    ok = db.update_shot(shot_id, target_ms=int(target_s * 1000))
    if not ok:
        _log("set_shot_target", f"镜头{shot_id}被拒绝(锁定)", ok=False, project=project)
        raise CommandError(f"镜头「{s.get('name')}」已锁定，拒绝修改。")
    _log("set_shot_target", f"镜头{shot_id}: {target_s}s", project=project)
    return {"ok": True, "shot_id": shot_id, "target_s": target_s,
            "note": "仅此镜头的建议时长已改，其它镜头未动。"}


def replace_shot(project, shot_id, asset_path, start_s=None, end_s=None):
    """替换单个镜头的素材。asset_path 必须是项目里已导入的真实素材。锁定镜头拒绝。"""
    db = _open(project)
    s = db.get_shot(shot_id)
    if not s:
        raise CommandError(f"镜头 {shot_id} 不存在。")
    asset_path = str(asset_path)
    asset = None
    for a in db.get_assets():
        if a.get("path") == asset_path:
            asset = a
            break
    if asset is None and not Path(asset_path).exists():
        raise CommandError(f"素材「{asset_path}」不在项目素材库中，也不是存在的视频文件。"
                           "不能虚构素材；请先用 list_assets 查看可用素材。")
    p = media.probe(asset_path)
    total = p.get("duration_ms", 0) / 1000.0
    start_s = float(start_s) if start_s is not None else 0.0
    end_s = float(end_s) if end_s is not None else total
    if end_s <= start_s or end_s > total + 0.05:
        raise CommandError(f"起止时间无效（素材总长 {total:.2f} 秒）。")
    ok = db.replace_shot_clip(shot_id, asset_path,
                              asset["id"] if asset else None, None,
                              int(start_s * 1000), int(end_s * 1000))
    if not ok:
        _log("replace_shot", f"镜头{shot_id}被拒绝(锁定)", ok=False, project=project)
        raise CommandError(f"镜头「{s.get('name')}」已锁定，拒绝修改。请用户先在界面解锁。")
    _log("replace_shot", f"镜头{shot_id}<-{Path(asset_path).name}", project=project)
    return {"ok": True, "shot_id": shot_id, "asset": Path(asset_path).name,
            "start_s": start_s, "end_s": end_s,
            "note": "仅此镜头已换素材，其它镜头未动。"}


def reorder_shots(project, shot_ids_in_order):
    """按给定顺序重排时间线镜头（只改 seq，不改任何镜头内容）。"""
    db = _open(project)
    ids = [int(i) for i in shot_ids_in_order]
    known = {s["shot_id"] for s in db.get_timeline()}
    if set(ids) != known or len(ids) != len(known):
        raise CommandError("shot_ids 必须恰好包含时间线上全部镜头各一次。")
    db.reorder_timeline(ids)
    _log("reorder_shots", f"{len(ids)}个镜头重排", project=project)
    return {"ok": True, "order": ids}


# ---------------- 导出（必须用户确认） ----------------

def export_video(project, output_name, confirm=False, ratio="3:4 竖版",
                 res="720p", fps=30, quality="标准", transition=None):
    """渲染并导出成片。【护栏】confirm=False 时一律拒绝——智能体必须先取得用户
    明确同意，再以 confirm=True 调用。缺素材的镜头会被跳过并列出。
    """
    db = _open(project)
    if not confirm:
        _log("export_video", "被拒绝：未经用户确认", ok=False, project=project)
        raise CommandError("导出被拒绝：智能体必须先向用户说明导出内容并取得明确同意，"
                           "然后带 confirm=True 重新调用。")
    if ratio not in config.EXPORT_SIZES:
        raise CommandError(f"不支持的比例「{ratio}」。可选：{'、'.join(config.EXPORT_SIZES)}")
    if res not in ("720p", "1080p"):
        raise CommandError("分辨率只支持 720p / 1080p。")

    out = config.EXPORT_DIR / Path(str(output_name)).name
    if out.suffix.lower() not in (".mp4",):
        out = out.with_suffix(".mp4")
    params = {"ratio": ratio, "res": res, "fps": int(fps),
              "crf": config.QUALITY_CRF.get(quality, 23),
              "transition": transition if transition is not None else config.DEFAULT_TRANSITION,
              "transition_s": config.DEFAULT_TRANSITION_S,
              "min_hold_ms": config.DEFAULT_MIN_HOLD_MS,
              "sub_transition_s": config.DEFAULT_SUB_TRANSITION_S}
    shots = db.get_timeline()
    r = video_editor.render_all(shots, params, db=db)
    if not r["segments"]:
        _log("export_video", "无可渲染镜头", ok=False, project=project)
        raise CommandError("没有任何可渲染的镜头（全部缺素材？）。")
    c = video_editor.concat_segments(r["segments"], out,
                                     transition=params["transition"],
                                     transition_s=params["transition_s"])
    if not c.get("ok"):
        _log("export_video", f"拼接失败:{c.get('error','')[:120]}", ok=False, project=project)
        raise CommandError(f"拼接失败：{c.get('error', '')[:300]}")
    info = video_editor.probe_output(out)
    _log("export_video", f"{out.name} {info.get('duration_ms',0)/1000:.1f}s "
                         f"渲染{r['rendered']} 缓存{r['cached']} 跳过{len(r['errors'])}",
         project=project)
    return {"ok": True, "output": str(out),
            "duration_s": round(info.get("duration_ms", 0) / 1000, 2),
            "width": info.get("width"), "height": info.get("height"),
            "rendered": r["rendered"], "cached_from_last_time": r["cached"],
            "skipped_missing": [e.get("shot_id") for e in r["errors"]],
            "note": "成片已生成；三轨(旁白/字幕/音乐)合成仍请走界面音频字幕页或告知用户。"}
