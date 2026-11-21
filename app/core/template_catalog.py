# -*- coding: utf-8 -*-
"""分镜模板目录（Phase C/D）：列出 templates/furniture 下可用 JSON。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .. import config


def templates_dir() -> Path:
    return config.ROOT / "templates" / "furniture"


def list_templates() -> List[dict]:
    out = []
    d = templates_dir()
    if not d.exists():
        return out
    for p in sorted(d.glob("*.json")):
        meta = {"path": str(p), "stem": p.stem, "name": p.stem, "product_type": "", "shots": 0}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            meta["product_type"] = data.get("product_type") or p.stem
            meta["name"] = data.get("product_type") or p.stem
            meta["shots"] = len(data.get("storyboards") or [])
        except Exception:
            pass
        out.append(meta)
    return out


def load_template_names(path: str) -> List[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [s.get("name") for s in (data.get("storyboards") or []) if s.get("name")]
