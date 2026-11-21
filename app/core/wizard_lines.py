# -*- coding: utf-8 -*-
"""【阶段十二新增】向导出片文案与素材分组的统一逻辑入口。

解决的问题（用户体检反馈）：
1. 一键出片每次重新生成固定标签，覆盖用户改过的字幕 —— 优先读用户自定义文案。
2. 标准模式读库里陈旧的 6 行文案，与 13 个镜头错位 —— 按当前时间线重建。
3. 中文旁白模式无配音却静默降级 —— 提供可用性检查，由界面层如实提示。
4. 护栏只校验程序自己生成的常量 —— 对用户自定义文字同样校验。
5. 标准字幕没扣叠化，越往后越飘 —— 按成片叠化重排时间。

设计原则：纯逻辑、无界面依赖、可单测；不修改任何原有函数，旧链路不受影响。
"""
import json
import os
from collections import Counter

from .. import config
from . import narration as nar

CUSTOM_LABELS_KEY = "wizard_custom_labels"   # settings：{shot_id: 文字}
CUSTOM_GROUPS_KEY = "wizard_custom_groups"   # settings：{asset_path: 组名}
EXTRA_GROUPS_KEY = "wizard_extra_groups"     # settings：[用户新建的空组名]


# ---------------- 用户自定义字幕 ----------------

def load_custom_labels(db):
    """读用户保存的自定义字幕文字。返回 {shot_id: str}。"""
    try:
        raw = (db.get_settings() or {}).get(CUSTOM_LABELS_KEY, "")
        data = json.loads(raw) if raw else {}
        return {str(k): str(v) for k, v in data.items() if str(v).strip()}
    except Exception:  # noqa: BLE001
        return {}


def save_custom_labels(db, mapping):
    """整组保存自定义字幕（只存非空的，空值表示恢复默认）。"""
    clean = {str(k): str(v).strip() for k, v in (mapping or {}).items()
             if str(v).strip()}
    db.set_setting(CUSTOM_LABELS_KEY, json.dumps(clean, ensure_ascii=False))
    return clean


def validate_custom_texts(texts):
    """护栏：用户自己写的字幕也不能含未核实宣称。返回违规说明列表。"""
    bad = []
    for t in texts:
        for w in nar.FORBIDDEN_CLAIMS:
            if w in str(t):
                bad.append(f"「{t}」含未核实词「{w}」")
                break
    return bad


# ---------------- 素材分组 ----------------

def load_custom_groups(db):
    try:
        raw = (db.get_settings() or {}).get(CUSTOM_GROUPS_KEY, "")
        data = json.loads(raw) if raw else {}
        return {str(k): str(v) for k, v in data.items()}
    except Exception:  # noqa: BLE001
        return {}


def save_custom_groups(db, mapping):
    clean = {str(k): str(v) for k, v in (mapping or {}).items() if str(v).strip()}
    db.set_setting(CUSTOM_GROUPS_KEY, json.dumps(clean, ensure_ascii=False))
    return clean


def load_extra_groups(db):
    try:
        raw = (db.get_settings() or {}).get(EXTRA_GROUPS_KEY, "")
        data = json.loads(raw) if raw else []
        return [str(x) for x in data if str(x).strip()]
    except Exception:  # noqa: BLE001
        return []


def save_extra_groups(db, names):
    clean = list(dict.fromkeys(str(x).strip() for x in (names or []) if str(x).strip()))
    db.set_setting(EXTRA_GROUPS_KEY, json.dumps(clean, ensure_ascii=False))
    return clean


def group_of(asset, overrides=None):
    """按视频真实所在文件夹得出组名，忽略脏 folder 数据（纯数字编号等）。"""
    ov = overrides or {}
    path = str(asset.get("path") or "")
    if path in ov and ov[path].strip():
        return ov[path].strip()
    parent = os.path.basename(os.path.dirname(path))
    return parent or "未分组"


def groups_summary(assets, overrides=None, extra=None):
    """返回 [(组名, 数量)]，按数量降序、组名升序。"""
    c = Counter(group_of(a, overrides) for a in assets)
    for name in (extra or []):
        c.setdefault(name, 0)
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))


# ---------------- 出片文案统一入口 ----------------

def align_to_transitions(lines, transition_ms=None):
    """按 xfade 叠化重排字幕起止点，消除累积漂移（不改任何文字）。"""
    if transition_ms is None:
        transition_ms = int(getattr(config, "DEFAULT_TRANSITION_S", 0.4) * 1000)
    n = len(lines)
    cum = 0
    out = []
    for i, ln in enumerate(lines):
        d = dict(ln)
        dur = max(0, int(ln.get("end_ms", 0)) - int(ln.get("start_ms", 0)))
        start = cum - i * transition_ms
        cum += dur
        end = cum - (i + 1) * transition_ms if i + 1 < n else cum - (n - 1) * transition_ms
        d["start_ms"] = max(0, start)
        d["end_ms"] = max(start + 200, end)
        out.append(d)
    return out


def _apply_custom(lines, custom):
    """把用户自定义文字覆盖到对应镜头（按 shot_id）。不动时间/版式。"""
    out = []
    for ln in lines:
        d = dict(ln)
        key = str(ln.get("shot_id") or "")
        if custom.get(key):
            d["text"] = custom[key]
        out.append(d)
    return out


def build_lines_for_export(db, shots, product, sub_style, custom_labels=None):
    """按当前时间线生成出片用文案。

    selling_badge：以卖点标签为底稿，用户改过的字覆盖上去，保留 kind 版式。
    standard：库里文案必须与当前镜头一一对应才用；否则按当前时间线重建，
              再按叠化重排时间。两种情况都套用自定义文字并做护栏校验。
    """
    custom = custom_labels if custom_labels is not None else load_custom_labels(db)
    warnings = []
    if sub_style == "selling_badge":
        base = nar.build_selling_lines(shots, product)["lines"]
        source, rebuilt = "selling_label", False
    else:
        saved = db.get_narration_lines()
        shot_ids = {str(s.get("shot_id")) for s in shots if _shot_has_asset(s)}
        saved_ids = {str(l.get("shot_id")) for l in saved if (l.get("text") or "").strip()}
        usable = bool(saved) and len(saved) == len(shot_ids) and saved_ids == shot_ids
        if usable:
            base = nar.decorate_lines(saved)
            source, rebuilt = "saved_narration", False
        else:
            base = nar.decorate_lines(nar.build_all(shots, product)["lines"])
            base = align_to_transitions(base)
            source, rebuilt = "rebuilt_narration", True
            warnings.append("文案已按当前镜头重新排好，旧的几句话不再使用。")

    lines = _apply_custom(base, custom)
    bad = (nar.validate_selling_labels(lines) if sub_style == "selling_badge"
           else validate_custom_texts([l.get("text", "") for l in lines]))
    return {"lines": lines, "source": source, "rebuilt": rebuilt,
            "warnings": warnings, "forbidden": bad, "custom_used": bool(custom)}


def _shot_has_asset(sh):
    if (sh.get("asset_path") or "").strip():
        return True
    raw = sh.get("sub_segments") or ""
    try:
        subs = json.loads(raw) if isinstance(raw, str) and raw.strip() else (raw or [])
    except Exception:  # noqa: BLE001
        subs = []
    return bool(subs) if isinstance(subs, list) else False


def narration_status(db, lines):
    """中文旁白可用性：返回 (有配音句数, 总句数, 是否齐全)。"""
    total = len(lines)
    have = 0
    for ln in lines:
        vp = ln.get("voice_path") or ""
        if vp:
            from pathlib import Path
            if Path(vp).exists():
                have += 1
    return have, total, (total > 0 and have == total)


def missing_shot_names(shots, shot_asset_fn):
    """返回还没有画面的镜头名列表（供出片前如实提醒）。"""
    return [str(s.get("name") or "未命名镜头") for s in shots
            if not shot_asset_fn(s)]
