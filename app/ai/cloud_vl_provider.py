# -*- coding: utf-8 -*-
"""云端视觉 Provider 骨架（Phase D）：默认关闭，带费用硬上限账本。

当前不发起真实外网调用：enabled 且 cost_cap>0 时仍要求显式 allow_upload，
否则直接报错，避免误传画面。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .. import config
from .vision_provider import BaseVisionProvider


LEDGER = config.LOG_DIR / "vision_cost.jsonl"


def _ledger_total() -> float:
    if not LEDGER.exists():
        return 0.0
    total = 0.0
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            total += float(json.loads(line).get("cny", 0) or 0)
        except Exception:
            continue
    return total


def append_ledger(entry: Dict[str, Any]):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class CloudVLProvider(BaseVisionProvider):
    name = "cloud_openai_vl"

    def __init__(self, cloud_cfg: Dict[str, Any] = None):
        self.cfg = cloud_cfg or {}
        self.cost_cap = float(self.cfg.get("cost_cap_cny") or 0)
        self.allow_upload = bool(self.cfg.get("allow_upload"))
        self.enabled = bool(self.cfg.get("enabled"))

    def analyze_segment(self, path, start_ms, end_ms, progress_cb=None):
        result = {
            "ok": False, "error": "", "provider": self.name,
            "labels": [], "metrics": {}, "suggested_tags": [],
            "need_review": True, "review_reasons": [],
        }
        if not self.enabled:
            result["error"] = "云端视觉未启用"
            return result
        if not self.allow_upload:
            result["error"] = "云端上传未授权（allow_upload=false），拒绝外传画面"
            return result
        if self.cost_cap <= 0:
            result["error"] = "费用上限为 0，拒绝任何云端调用"
            return result
        spent = _ledger_total()
        if spent >= self.cost_cap:
            result["error"] = f"已达费用上限 {self.cost_cap} 元（已用 {spent:.2f}）"
            return result
        # 骨架：不实际调用外网；记账 0 并提示未实现
        append_ledger({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "provider": self.name,
            "cny": 0,
            "note": "cloud stub — no network call",
            "path": str(path)[:80],
        })
        result["error"] = "云端 Provider 仅为骨架，尚未实现真实 API 调用"
        return result
