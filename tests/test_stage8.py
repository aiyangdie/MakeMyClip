# -*- coding: utf-8 -*-
"""阶段八测试：智能体操作层（commands.py）真实验证。

验证目标（用户拍板的护栏）：
1. 只读命令可用（列项目/列镜头/详情/列素材/日志）。
2. 单镜头修改只影响它自己（铁律）。
3. 锁定镜头拒绝修改（数据库层强制，智能体绕不过）。
4. 导出未经用户确认(confirm=False)一律拒绝；确认后能真实出片。
5. 全部操作写入审计日志。
6. 虚构素材被拒绝（不能拿素材库外/不存在的文件当素材）。

测试项目使用 _stage7_e2e.db 的副本 _stage8_agent.db，不碰任何真实项目。
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import commands, config  # noqa: E402
from app import db as dbmod       # noqa: E402

SRC = config.DB_DIR / "_stage7_e2e.db"
DB = config.DB_DIR / "_stage8_agent.db"

results = []


def check(name, ok, note=""):
    results.append({"name": name, "ok": bool(ok), "note": str(note)})
    print(("[PASS] " if ok else "[FAIL] ") + name + (f"  {note}" if note else ""))


# ---------- 准备 ----------
shutil.copyfile(SRC, DB)
P = "_stage8_agent"

db = dbmod.ProjectDB(str(DB))
before = {s["shot_id"]: dict(s) for s in db.get_timeline()}
before_targets = {s["shot_id"]: s.get("target_ms") for s in db.get_timeline()}

# 1. 列出项目
projs = commands.list_projects()
check("列出项目包含测试项目", any(p["name"] == "_stage8_agent" for p in projs),
      f"{len(projs)} 个项目")

# 2. 列出镜头（只读）
shots = commands.list_shots(P)
check("列出时间线镜头", len(shots) >= 6, f"{len(shots)} 个镜头")
names = [s["name"] for s in shots]

# 3. 镜头详情（含素材时长）
sample = next(s for s in shots if s["asset"])
det = commands.get_shot(P, sample["shot_id"])
check("镜头详情含素材总时长", det.get("asset_duration_s", 0) > 0,
      f"{det['name']} 素材 {det.get('asset_duration_s')}s")

# 4. 列出素材
assets = commands.list_assets(P)
check("列出项目素材", len(assets) > 0, f"{len(assets)} 条")

# 5. 改建议时长：只影响它自己
tgt = next(s for s in shots if s["asset"] and not s["locked"] and not s["linked"])
r = commands.set_shot_target(P, tgt["shot_id"], 2.8)
after = {s["shot_id"]: s for s in db.get_timeline()}
others_same = all(after[k]["target_ms"] == before_targets[k]
                  for k in after if k != tgt["shot_id"])
check("改建议时长仅影响该镜头", r["ok"] and after[tgt["shot_id"]]["target_ms"] == 2800
      and others_same, f"镜头{tgt['shot_id']}→2.8s，其它未动")

# 6. 改起止时间：只影响它自己 + 清缓存标识
r = commands.set_shot_time(P, tgt["shot_id"], 1.0, 3.0)
after2 = {s["shot_id"]: s for s in db.get_timeline()}
others_same2 = all(
    (after2[k]["start_ms"], after2[k]["end_ms"], after2[k]["cache_key"]) ==
    (after[k]["start_ms"], after[k]["end_ms"], after[k]["cache_key"])
    for k in after2 if k != tgt["shot_id"])
check("改起止时间仅影响该镜头", r["ok"] and after2[tgt["shot_id"]]["start_ms"] == 1000
      and after2[tgt["shot_id"]]["cache_key"] == "" and others_same2)

# 7. 非法起止被拒绝
try:
    commands.set_shot_time(P, tgt["shot_id"], 5.0, 5.0)
    check("非法起止时间被拒绝", False)
except commands.CommandError as e:
    check("非法起止时间被拒绝", "结束时间" in str(e))

# 8. 锁定镜头拒绝（模拟用户在界面锁定）
victim = next(s for s in shots if s["asset"] and not s["locked"] and s["shot_id"] != tgt["shot_id"])
db.update_shot(victim["shot_id"], locked=True)
try:
    commands.set_shot_target(P, victim["shot_id"], 5.0)
    check("锁定镜头拒绝修改", False)
except commands.CommandError as e:
    cur = db.get_shot(victim["shot_id"])
    check("锁定镜头拒绝修改", "锁定" in str(e) and cur["target_ms"] == before_targets[victim["shot_id"]],
          f"报错含'锁定'，原值未动")

# 9. 虚构素材被拒绝
try:
    commands.replace_shot(P, tgt["shot_id"], "C:/不存在/虚构素材.mov")
    check("虚构素材被拒绝", False)
except commands.CommandError as e:
    check("虚构素材被拒绝", "虚构素材" in str(e) or "不存在" in str(e))

# 10. 换真实素材：只影响它自己
real_asset = assets[0]
r = commands.replace_shot(P, tgt["shot_id"], real_asset["path"], 0, 2.0)
after3 = {s["shot_id"]: s for s in db.get_timeline()}
others_same3 = all(
    (after3[k]["asset_path"], after3[k]["start_ms"]) ==
    (after2[k]["asset_path"], after2[k]["start_ms"])
    for k in after3 if k != tgt["shot_id"])
check("换真实素材仅影响该镜头", r["ok"] and after3[tgt["shot_id"]]["asset_path"] == real_asset["path"]
      and others_same3, f"换成 {real_asset['name']}")

# 11. 导出未经确认 → 拒绝
try:
    commands.export_video(P, "_stage8_should_not_exist.mp4", confirm=False)
    check("未确认导出被拒绝", False)
except commands.CommandError as e:
    check("未确认导出被拒绝", "拒绝" in str(e) and "同意" in str(e) and
          not (config.EXPORT_DIR / "_stage8_should_not_exist.mp4").exists(),
          f"报错：{str(e)[:30]}…")

# 12. 确认后真实导出（渲染，缓存大多复用）
r = commands.export_video(P, "_阶段八_智能体导出.mp4", confirm=True, ratio="3:4 竖版")
check("确认后真实导出成功", r["ok"] and Path(r["output"]).exists(),
      f"{r['duration_s']}s {r['width']}x{r['height']} 渲染{r['rendered']} 缓存{r['cached_from_last_time']}")
check("导出比例符合3:4竖版", r["width"] == 720 and r["height"] == 960)

# 13. 审计日志完整（含被拒绝的记录）
log = commands.read_log(50)
has_reject = any(l["action"] == "export_video" and not l["ok"] for l in log)
has_ok = any(l["action"] == "export_video" and l["ok"] for l in log)
has_edit = any(l["action"] == "set_shot_target" and l["ok"] for l in log)
check("审计日志完整（拒绝/成功/修改均有记录）", has_reject and has_ok and has_edit,
      f"最近{len(log)}条")

n_pass = sum(1 for x in results if x["ok"])
out = {"stage": 8, "total": len(results), "pass": n_pass,
       "ok": n_pass == len(results), "results": results}
Path("tests/test_result_stage8.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n阶段八：{n_pass}/{len(results)} 通过")
sys.exit(0 if n_pass == len(results) else 1)
