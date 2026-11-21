# -*- coding: utf-8 -*-
"""Phase A–D 综合单测（不依赖桌面视频素材）。"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, db as dbmod
from app.ai import vision_config, vision_provider
from app.core import missing_export, export_qc, template_catalog, score_calibrator

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append({"name": name, "pass": bool(cond), "detail": detail})
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f" — {detail}" if detail else ""))


print("=" * 70)
print("Phase A–D 综合测试")
print("=" * 70)

# A: missing export
print("\n[A] 缺片导出")
rows = missing_export.collect_missing({
    "1": {"missing": True, "reason": "无候选", "advice": "补拍整体"},
    "2": {"missing": False},
}, storyboards=[{"id": 1, "name": "产品整体亮相"}])
check("收集到 1 条缺失", len(rows) == 1, str(rows))
td = tempfile.mkdtemp(prefix="mmc_miss_")
txt, csvp = missing_export.export_missing(
    {"1": {"missing": True, "reason": "x", "advice": "y"}}, td,
    storyboards=[{"id": 1, "name": "整体"}])
check("写出 txt", Path(txt).exists())
check("写出 csv", Path(csvp).exists())

# B: vision config + factory fallback
print("\n[B] 视觉配置与降级")
cfg = vision_config.load_vision_config()
check("有 provider 键", "provider" in cfg)
check("local.allow_upload 强制 False", cfg["local"].get("allow_upload") is False)
p = vision_provider.provider_factory("heuristic_local_v1")
check("启发式可创建", p.name == "heuristic_local_v1")
# VLM 未启动时应降级
p2 = vision_provider.provider_factory("ollama_qwen_vl")
check("VLM 未就绪降级启发式", p2.name == "heuristic_local_v1", p2.name)
check("带降级标记", getattr(p2, "degraded_from", None) == "ollama_qwen_vl")

# C: templates + export qc structure
print("\n[C] 模板与质检结构")
tpls = template_catalog.list_templates()
check("至少 2 套模板", len(tpls) >= 2, str([t["stem"] for t in tpls]))
check("含 desk_lamp", any(t["stem"] == "desk_lamp" for t in tpls))
qc = export_qc.check_export(str(Path(td) / "nope.mp4"))
check("缺文件质检失败", qc["ok"] is False)

# D: edit history + calibration isolation + MCP command helpers
print("\n[D] 编辑历史 / 校准隔离 / 命令")
dbp = Path(td) / "phase.db"
db = dbmod.ProjectDB(str(dbp))
db.set_storyboard_template(str(config.ROOT / "templates" / "furniture" / "desk_lamp.json"))
db.add_edit_history("test", "x", {"a": 1}, "note")
hist = db.list_edit_history(5)
check("edit_history 可写可读", len(hist) >= 1)
key = db._calibration_settings_key()
check("校准键含模板名", "desk_lamp" in key, key)

from app import commands
tpls2 = commands.list_storyboard_templates()
check("commands.list_storyboard_templates", len(tpls2.get("templates", [])) >= 2)

# test_paths helper
from tests import test_paths as tp
check("media_root 可调用", tp.media_root() is None or Path(tp.media_root()).exists())

passed = sum(1 for r in RESULTS if r["pass"])
failed = sum(1 for r in RESULTS if not r["pass"])
print("\n" + "=" * 70)
print(f"结果：通过 {passed} / 失败 {failed} / 合计 {len(RESULTS)}")
print("=" * 70)
sys.exit(0 if failed == 0 else 1)
