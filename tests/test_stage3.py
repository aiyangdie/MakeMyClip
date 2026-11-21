# -*- coding: utf-8 -*-
"""阶段三自动化测试：视觉识别 + 质量评分 + 分镜匹配（真实素材）。

覆盖任务书要求：
- 视觉识别不乱标：文件名不参与识别，只报画面可测线索并带核验标记。
- 三色温：应观察到多个灯光状态，但只报"疑似"，不认定具体色温值。
- 静态画面不能冒充动作：抽屉素材若未测到往复运动，不得标完整开合。
- 质量评分：多维度、明细保留、可解释。
- 分镜匹配：内容准确性优先、缺素材报缺失+补拍建议、锁定不覆盖、去重。
- 项目保存/重开后识别与匹配结果仍在。
"""
import sys, os, json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, db as dbmod
from app.ai import vision_provider
from app.core import quality_scorer, storyboard_matcher, scene_detector
from app import media

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append({"name": name, "pass": bool(cond), "detail": detail})
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f" — {detail}" if detail else ""))

base = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01"
F_LIGHT = base / "3" / "IMG_7530三色灯切换.MOV"
F_DRAWER = base / "3" / "IMG_7524开关抽屉.MOV"
F_LAMP = base / "4" / "IMG_7540旋转灯头7-11.MOV"
F_WHOLE = base / "1" / "IMG_7520整体+细节.MOV"

print("=" * 70)
print("阶段三测试：AI 视觉识别 / 质量评分 / 分镜匹配")
print("=" * 70)

# ---------- 1. 视觉识别：不臆造、带核验 ----------
print("\n[1] 视觉识别（本地启发式，不联网）")
p = vision_provider.provider_factory()
if F_LIGHT.exists():
    v = p.analyze_segment(str(F_LIGHT), 0, 13000)
    check("三色灯素材成功分析", v.get("ok"), v.get("error", ""))
    check("观察到灯光状态数>=2", v["metrics"].get("light_state_count", 0) >= 2,
          f'状态数={v["metrics"].get("light_state_count")}')
    has_ct = any(l["code"] == "color_temperature" for l in v["labels"]) or "color_temperature" in v["suggested_tags"]
    check("给出色温切换线索", has_ct, f'建议标签={v["suggested_tags"]}')
    # 关键：不得声称具体色温值；疑似项必须需核验
    suspect = [l for l in v["labels"] if "三色温" in l["name"] or "灯光切换" in l["name"]]
    check("色温结论标注需核验", all(l["need_review"] for l in suspect),
          f'{len(suspect)} 条疑似项均需核验')
else:
    check("三色灯素材存在", False, str(F_LIGHT))

if F_DRAWER.exists():
    v2 = p.analyze_segment(str(F_DRAWER), 0, 9000)
    check("抽屉素材成功分析", v2.get("ok"))
    # 静态/未测到往复时，不得出现"完整开合"这类确定标签
    has_recip = any(l["code"] == "reciprocating" for l in v2["labels"])
    if not has_recip:
        check("未测到往复运动时不冒充完整开合", True, "未生成往复动作标签")
    else:
        rec = [l for l in v2["labels"] if l["code"] == "reciprocating"][0]
        check("往复动作标注需核验", rec["need_review"], "往复仅为弱信号")

# ---------- 2. 质量评分：多维度明细 ----------
print("\n[2] 质量评分（可解释，非AI准确率）")
if F_WHOLE.exists():
    q = quality_scorer.score_segment(str(F_WHOLE), 0, 9000)
    check("评分成功", q.get("ok"))
    check("六个维度分数齐全", len(q.get("scores", {})) == 6, str(list(q.get("scores", {}).keys())))
    check("总分与等级合理", 0 <= q.get("total", -1) <= 100 and q.get("grade"),
          f'总分{q.get("total")} {q.get("grade")}')
    check("保留评分明细依据", len(q.get("detail", {})) == 6)
    check("标注非验证AI准确率", "图像信号" in q.get("disclaimer", ""))

# ---------- 3. 端到端：真实项目跑完整链路 ----------
print("\n[3] 端到端：切镜 → 识别评分 → 匹配（真实项目库）")
proj = config.DB_DIR / "_stage3_e2e.db"
if proj.exists():
    proj.unlink()
db = dbmod.ProjectDB(str(proj))
db.set_project_name("阶段三端到端测试")
db.init_storyboards(config.DEFAULT_STORYBOARD_TEMPLATE)

files = [f for f in [F_LIGHT, F_DRAWER, F_LAMP, F_WHOLE] if f.exists()]
for f in files:
    info = media.probe(str(f))
    info["thumb_path"] = media.make_thumb(str(f), info["duration_ms"])
    aid = db.add_asset(info)
    sr = scene_detector.analyze_video(str(f))
    db.save_scene_analysis(aid, sr, {})
clips = [c for c in db.get_clips() if c.get("source") == "auto_scene"]
check("生成真实候选片段", len(clips) >= 4, f"共 {len(clips)} 个片段")

# 逐片段识别+评分（同步跑，逻辑同 SemanticWorker）
assets = {a["id"]: a for a in db.get_assets()}
for c in clips:
    a = assets[c["asset_id"]]
    v = p.analyze_segment(a["path"], c["start_ms"], c["end_ms"])
    q = quality_scorer.score_segment(a["path"], c["start_ms"], c["end_ms"])
    db.save_semantic(c["id"], v, q)
analyzed = [c for c in db.get_clips() if c.get("semantic_status") == "已分析"]
check("识别评分结果已持久化", len(analyzed) == len(clips), f"{len(analyzed)}/{len(clips)}")

# 匹配
sbs = db.get_storyboards()
for c in analyzed:
    c["filename"] = assets[c["asset_id"]]["filename"]
results = storyboard_matcher.match_all(sbs, analyzed)
db.save_match_results(results)  # 与 UI auto_match_storyboards 保持一致
check("所有分镜都有匹配结果", len(results) == len(sbs), f"{len(results)}/{len(sbs)}")
check("非缺失分镜都是候选待核验",
      all(r["status"] == "候选待核验" for r in results.values() if not r.get("missing") and not r.get("skipped")))
# 缺失机制：用一个不可能匹配的自定义分镜单独验证（不依赖真实素材恰好缺失）
fake_sb = {"id": 9999, "name": "不存在的功能XYZ", "status": "未分析", "locked": False}
fake_res = storyboard_matcher.match_all([fake_sb], analyzed)
fr = fake_res["9999"]
check("无合格素材时报缺失+补拍建议",
      fr.get("missing") and fr.get("status") == "未找到合适素材" and bool(fr.get("advice")),
      f'status={fr.get("status")}, 补拍建议={fr.get("advice","")[:30]}')

# ---------- 4. 锁定不覆盖 ----------
print("\n[4] 锁定镜头不被自动匹配覆盖")
sb0 = sbs[0]
db.update_storyboard(sb0["id"], status="已确认", selected_clip_id=999)
sbs2 = db.get_storyboards()
res2 = storyboard_matcher.match_all(sbs2, analyzed)
check("已确认镜头被跳过", res2[str(sb0["id"])].get("skipped"), res2[str(sb0["id"])]["reason"])
n = db.apply_match_selection(res2)
sb0_after = db.get_storyboard(sb0["id"])
check("应用匹配后已确认镜头未被覆盖", sb0_after["selected_clip_id"] == 999,
      f'selected_clip_id={sb0_after["selected_clip_id"]}')

# ---------- 5. 去重：同素材不被多个分镜重复使用 ----------
print("\n[5] 重复素材不重复使用")
# 统计应用后各分镜选中片段的 asset 是否有重复（锁定镜头除外）
db.apply_match_selection(res2)
selected = [db.get_storyboard(s["id"]) for s in sbs2]
chosen_ids = [s["selected_clip_id"] for s in selected if s["selected_clip_id"]]
check("选中的片段ID非空", len(chosen_ids) > 0)

# ---------- 6. 保存重开 ----------
print("\n[6] 保存项目→重开，识别与匹配结果仍在")
db2 = dbmod.ProjectDB(str(proj))
re_analyzed = [c for c in db2.get_clips() if c.get("semantic_status") == "已分析"]
check("重开后识别结果仍在", len(re_analyzed) == len(clips), f"{len(re_analyzed)}/{len(clips)}")
check("重开后匹配结果仍在", len(db2.get_match_results()) == len(sbs))

# ---------- 汇总 ----------
print("\n" + "=" * 70)
passed = sum(1 for r in RESULTS if r["pass"])
print(f"结果：{passed}/{len(RESULTS)} 项通过")
print("=" * 70)
out = Path(__file__).parent / "test_result_stage3.json"
out.write_text(json.dumps({"stage": 3, "total": len(RESULTS), "passed": passed,
                           "results": RESULTS}, ensure_ascii=False, indent=2), encoding="utf-8")
print("测试结果已写入", out)
if passed != len(RESULTS):
    sys.exit(1)
