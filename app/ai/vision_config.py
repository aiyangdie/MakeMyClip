# -*- coding: utf-8 -*-
"""视觉 Provider 配置（本地优先、默认不上传）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .. import config

DEFAULT = {
    "provider": "heuristic_local_v1",
    "local": {
        "name": "ollama_qwen_vl",
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen3-vl:4b-instruct-q4_K_M",
        "timeout_sec": 120,
        "sample_interval_ms": 800,
        "max_samples": 12,
        "allow_upload": False,
    },
    "cloud": {
        "enabled": False,
        "base_url": "",
        "api_key": "",
        "model": "",
        "cost_cap_cny": 0,
        "allow_upload": False,
    },
    "fallback": "heuristic_local_v1",
}


def config_path() -> Path:
    return config.ROOT / "config" / "vision.json"


def load_vision_config() -> Dict[str, Any]:
    p = config_path()
    if not p.exists():
        return json.loads(json.dumps(DEFAULT))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(DEFAULT))
    out = json.loads(json.dumps(DEFAULT))
    out.update({k: v for k, v in data.items() if k in out})
    if isinstance(data.get("local"), dict):
        out["local"].update(data["local"])
    if isinstance(data.get("cloud"), dict):
        out["cloud"].update(data["cloud"])
    # 硬护栏：上传默认关
    out["local"]["allow_upload"] = False
    if not out["cloud"].get("enabled"):
        out["cloud"]["allow_upload"] = False
    return out


def active_provider_name(cfg: Dict[str, Any] = None) -> str:
    cfg = cfg or load_vision_config()
    name = (cfg.get("provider") or "heuristic_local_v1").strip()
    return name or "heuristic_local_v1"
