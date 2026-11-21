# -*- coding: utf-8 -*-
"""导出后自动质检（Phase C）。

检查项尽量用本机 probe / 文件体积，不依赖桌面素材路径。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .. import media


def check_export(path: str, expect: Dict[str, Any] = None) -> Dict[str, Any]:
    """返回 {ok, grade, checks:[{name,ok,detail}], summary}。"""
    expect = expect or {}
    p = Path(path)
    checks: List[dict] = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    if not p.exists():
        return {"ok": False, "grade": "失败", "checks": [{"name": "文件存在", "ok": False, "detail": str(p)}],
                "summary": "成片文件不存在"}

    size = p.stat().st_size
    add("文件非空", size > 10_000, f"{size} bytes")

    info = {}
    try:
        info = media.probe(str(p)) or {}
    except Exception as e:  # noqa: BLE001
        add("可探测", False, str(e))
        return {"ok": False, "grade": "失败", "checks": checks, "summary": "无法探测成片"}

    add("可探测", True, f"{info.get('width')}x{info.get('height')} {info.get('duration_ms')}ms")
    dur = int(info.get("duration_ms") or 0)
    add("时长合理", 3_000 <= dur <= 120_000, f"{dur} ms")
    w, h = int(info.get("width") or 0), int(info.get("height") or 0)
    add("有分辨率", w >= 320 and h >= 320, f"{w}x{h}")
    if expect.get("ratio") == "3:4":
        # 允许小误差
        ok_r = h > 0 and abs((w / h) - (3 / 4)) < 0.08
        add("接近3:4", ok_r, f"ratio={w/h if h else 0:.3f}")
    if expect.get("min_w"):
        add("宽度达标", w >= int(expect["min_w"]), f"w={w}")
    has_audio = bool(info.get("has_audio"))
    want_audio = expect.get("require_audio")
    if want_audio is True:
        add("含音轨", has_audio, "has_audio")
    elif want_audio is False:
        add("音轨可选", True, f"has_audio={has_audio}")

    failed = [c for c in checks if not c["ok"]]
    ok = len(failed) == 0
    grade = "通过" if ok else ("警告" if len(failed) <= 1 else "未通过")
    summary = "成片质检通过" if ok else ("；".join(f"{c['name']}:{c['detail']}" for c in failed))
    return {"ok": ok, "grade": grade, "checks": checks, "summary": summary,
            "probe": {k: info.get(k) for k in ("width", "height", "duration_ms", "fps", "has_audio")}}


def save_qc_report(qc: dict, out_path: str) -> str:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)
