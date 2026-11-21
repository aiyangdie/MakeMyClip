# -*- coding: utf-8 -*-
"""阶段七测试：按淘宝主图视频规范分配每镜头建议时长。

用户需求：不重要的镜头快一点、重要的慢一点；上一版全局 3.5s 停留导致整片太慢。
查证淘宝规范（2025）：时长 3-60s 允许、最佳 15-30s、前 3 秒抓眼球；
主图视频 9:16 上传后商详页不展示，官方推荐 3:4 或 1:1。

本测试验证：
  [0] 模板含 shot_targets 默认节奏；3:4 比例已加入导出选项
  [1] 建议时长两头起作用：长素材(16s)截短到 4s；短素材(1.5s)定格补足到 2.5s
  [2] 建议时长=0 回退：素材多长用多长（原行为不变）
  [3] 铁律：改一个镜头的建议时长，只有它的缓存标识变，其它镜头标识不变
  [4] 联动镜头子片段各自建议时长：按下2.5s + 灯变7.5s - 叠化0.4s ≈ 9.6s
  [5] 时间线镜头行带建议时长；模板套用不覆盖手动改过的值
  [6] 成片总长落在淘宝最佳区间 15-30s（3:4 竖版 720p）
  [7] 字幕/文案时长与渲染结果对齐（不再按素材原长计算）
"""
import sys, os, json, copy
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, db as dbmod, media
from app.core import video_editor as ve
from app.core import storyboard_matcher as sm
from app.core import narration

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append({"name": name, "pass": bool(cond), "detail": detail})
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f" — {detail}" if detail else ""))

base = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01"
F_WHOLE  = base / "1" / "IMG_7520整体+细节.MOV"
F_LIGHT  = base / "3" / "IMG_7530三色灯切换.MOV"
F_DRAWER = base / "3" / "IMG_7524开关抽屉.MOV"
F_HEAD   = base / "4" / "IMG_7540旋转灯头7-11.MOV"

print("=" * 72)
print("阶段七测试：按淘宝主图视频规范分配镜头节奏（真实素材）")
print("=" * 72)

# ---------- 0. 模板与比例 ----------
print("\n[0] 模板默认节奏与新比例")
tpl = sm.load_template()
tg = (tpl or {}).get("shot_targets", {})
check("模板含 shot_targets 默认节奏", bool(tg), f'{len([k for k in tg if not k.startswith("_")])} 个镜头')
check("3:4 比例已加入导出选项", "3:4 竖版" in config.EXPORT_SIZES)
check("3:4 尺寸正确(720p=720x960)", config.EXPORT_SIZES["3:4 竖版"]["720p"] == (720, 960))
check("全局兜底停留默认已改为0", config.DEFAULT_MIN_HOLD_MS == 0)

# ---------- 构造项目并套用模板节奏 ----------
proj = config.DB_DIR / "_stage7_e2e.db"
if proj.exists():
    proj.unlink()
db = dbmod.ProjectDB(str(proj))
db.set_project_name("阶段七端到端")
db.init_storyboards(config.DEFAULT_STORYBOARD_TEMPLATE)
n_applied = db.apply_storyboard_targets(tg)
check("模板默认节奏已套用到分镜", n_applied >= 12, f"套用 {n_applied} 个")

# ---------- 5. 套用逻辑：不覆盖手动改过的值 ----------
sbs = db.get_storyboards()
one = next(s for s in sbs if s["name"] == "灯头旋转")
db.update_storyboard(one["id"], target_ms=12345)
n2 = db.apply_storyboard_targets(tg)
cur = next(s for s in db.get_storyboards() if s["name"] == "灯头旋转")
check("重复套用不覆盖手动改过的值", cur["target_ms"] == 12345, f'手动值 {cur["target_ms"]}ms 保留')
db.update_storyboard(one["id"], target_ms=int(tg["灯头旋转"]))  # 还原，避免测试值漏进成片

asset_paths = {"whole": str(F_WHOLE), "light": str(F_LIGHT),
               "drawer": str(F_DRAWER), "head": str(F_HEAD)}
aids = {}
for k, p in asset_paths.items():
    info = media.probe(p)
    aids[k] = db.add_asset(info)
    db.save_scene_analysis(aids[k], {"shots": [{"index": 1, "start_ms": 0,
                              "end_ms": info.get("duration_ms", 8000)}],
                             "boundaries": [], "light_events": []}, {})

sbs = db.get_storyboards()
by_name = {s["name"]: s for s in sbs}
plan = [
    ("产品整体亮相", "whole"),
    ("台面材质和边缘", "whole"),
    ("抽屉开合", "drawer"),
    ("灯头旋转", "head"),
    ("三色温切换", "light"),     # 联动镜头载体
    ("整体收尾", "whole"),
]
for name, key in plan:
    c = db.get_clips_by_asset(aids[key])[0]
    db.update_storyboard(by_name[name]["id"], selected_clip_id=c["id"])
db.rebuild_timeline_from_storyboards()

timeline = db.get_timeline()
# 台面镜头真的设成 1.5s 短片段（阶段六同款场景）
short = next(s for s in timeline if s["name"] == "台面材质和边缘")
db.update_shot(short["shot_id"], start_ms=2500, end_ms=4000)

# 三色温切换 -> 按钮联动镜头：两段真实画面 + 各自建议时长（模板节奏）
lk = tpl["linked_shots"][0]
tgt_map = tg
target = next(s for s in db.get_timeline() if s["name"] == "三色温切换")
link_subs = []
for seg in lk["segments"]:
    real_path = next((p for p in asset_paths.values() if Path(p).name == seg["asset_hint"]),
                     asset_paths["light"])
    t_key = f'按钮触发三色灯:{seg.get("role", "")}'
    link_subs.append({"asset_path": real_path,
                      "start_ms": seg["start_ms"], "end_ms": seg["end_ms"],
                      "role": seg.get("role", ""),
                      "target_ms": int(tgt_map.get(t_key, 0))})
db.set_linked_shot(target["shot_id"], link_subs, name="按钮触发三色灯")
timeline = db.get_timeline()
bound = [s for s in timeline if s.get("asset_path") or s.get("sub_segments")]
print(f"\n[准备] 时间线 {len(timeline)} 镜头，有画面 {len(bound)} 个（含联动 1 个）")

check("镜头行带上模板建议时长",
      all((s.get("target_ms") or 0) == tgt_map.get(s["name"], 0)
          for s in bound if not s.get("sub_segments") and s["name"] in tgt_map),
      "整体4s/台面2.5s/抽屉5s/灯头4s/收尾4s")

# ---------- 1. 建议时长两头起作用 ----------
print("\n[1] 建议时长：长素材截短 / 短素材定格补足")
ep = {"ratio": "3:4 竖版", "res": "720p", "fps": 30, "crf": 23,
      "min_hold_ms": 0, "transition": "fade", "transition_s": 0.4,
      "sub_transition_s": 0.4}
whole_shot = next(s for s in bound if s["name"] == "产品整体亮相")
check("整体镜头素材原本16.1s太长", (whole_shot["end_ms"] - whole_shot["start_ms"]) > 15000,
      f'{(whole_shot["end_ms"]-whole_shot["start_ms"])/1000:.1f}s')
r1 = ve.render_shot(whole_shot, ep)
i1 = ve.probe_output(r1["path"])
check("长素材(16.1s)按建议截短到4s", r1["ok"] and 3800 <= i1["duration_ms"] <= 4200,
      f'{i1["duration_ms"]/1000:.2f}s')
check("3:4比例输出正确(720x960)", i1["width"] == 720 and i1["height"] == 960,
      f'{i1["width"]}x{i1["height"]}')

short_shot = next(s for s in bound if s["name"] == "台面材质和边缘")
r2 = ve.render_shot(short_shot, ep)
i2 = ve.probe_output(r2["path"])
check("短素材(1.5s)定格补足到2.5s", r2["ok"] and 2300 <= i2["duration_ms"] <= 2700,
      f'{i2["duration_ms"]/1000:.2f}s')

# ---------- 2. 建议时长=0 回退 ----------
print("\n[2] 建议时长=0：素材多长用多长（原行为）")
no_target = dict(short_shot); no_target["target_ms"] = 0
r3 = ve.render_shot(no_target, ep)
i3 = ve.probe_output(r3["path"])
check("建议时长0且兜底0 -> 保持1.5s原长",
      r3["ok"] and 1400 <= i3["duration_ms"] <= 1700, f'{i3["duration_ms"]/1000:.2f}s')
no_target2 = dict(no_target); no_target2.pop("target_ms", None)
ep_hold = dict(ep); ep_hold["min_hold_ms"] = 3500
r4 = ve.render_shot({**short_shot, "target_ms": 0}, ep_hold)
i4 = ve.probe_output(r4["path"])
check("建议时长0但全局兜底3.5s -> 补足到3.5s（阶段六行为兼容）",
      r4["ok"] and 3300 <= i4["duration_ms"] <= 3700, f'{i4["duration_ms"]/1000:.2f}s')

# ---------- 3. 铁律：改一个镜头的建议时长只影响它自己 ----------
print("\n[3] 铁律：改建议时长只影响这一个镜头")
keys_before = {s["shot_id"]: ve.cache_key_for(s, ep) for s in bound if not s.get("sub_segments")}
drawer = next(s for s in bound if s["name"] == "抽屉开合")
drawer_new = dict(drawer); drawer_new["target_ms"] = 6000
keys_after = dict(keys_before)
keys_after[drawer["shot_id"]] = ve.cache_key_for(drawer_new, ep)
changed = [sid for sid in keys_before if keys_before[sid] != keys_after[sid]]
check("只有抽屉镜头的缓存标识变化", changed == [drawer["shot_id"]], f"变化={changed}")
check("其它镜头缓存标识全部不变",
      all(keys_after[sid] == keys_before[sid] for sid in keys_before if sid != drawer["shot_id"]))

# ---------- 4. 联动镜头子片段各自建议时长 ----------
print("\n[4] 联动镜头：按下2.5s + 灯变7.5s - 叠化0.4s")
linked = next(s for s in bound if s.get("sub_segments"))
rl = ve.render_linked_shot(linked, ep)
il = ve.probe_output(rl["path"])
check("联动镜头按子片段建议时长渲染", rl["ok"] and 9200 <= il["duration_ms"] <= 10000,
      f'{il["duration_ms"]/1000:.2f}s（预期约9.6s）')

# ---------- 6. 成片总长落在淘宝最佳区间 ----------
print("\n[6] 成片：3:4 竖版 720p，叠化，总长应落在 15-30s")
res = ve.render_all(bound, ep)
outD = config.EXPORT_DIR / "阶段七_淘宝节奏成片.mp4"
cd = ve.concat_segments(res["segments"], str(outD), transition="fade", transition_s=0.4)
pd_ = ve.probe_output(str(outD))
check("成片生成成功", cd["ok"], cd.get("error", "")[:100])
check("成片是3:4比例(720x960)", pd_["width"] == 720 and pd_["height"] == 960,
      f'{pd_["width"]}x{pd_["height"]}')
check("总长落在淘宝最佳区间15-30s", 15000 <= pd_["duration_ms"] <= 30000,
      f'{pd_["duration_ms"]/1000:.1f}s')
check("前3秒是开场整体画面（首镜头即整体亮相）",
      bound[0]["name"] == "产品整体亮相" and (bound[0].get("target_ms") or 0) >= 3000,
      f'开场建议{(bound[0].get("target_ms") or 0)/1000:.1f}s')

# ---------- 7. 字幕时长与渲染结果对齐 ----------
print("\n[7] 文案/字幕时长按建议时长对齐")
nres = narration.build_all(bound, {"name": "测试床头柜", "color": "白色", "material": "板材"})
lines = nres["lines"]
check("生成文案行数=有画面镜头数", len(lines) == len(bound), f'{len(lines)} 行')
l0 = lines[0]
check("首句时长=开场建议时长4s", l0["end_ms"] - l0["start_ms"] == 4000,
      f'{l0["end_ms"]-l0["start_ms"]}ms')
ll = next(l for l in lines if l["shot_id"] == linked["shot_id"])
check("联动镜头字幕时长=9.6s(按下2.5+灯变7.5-叠化0.4)",
      ll["end_ms"] - ll["start_ms"] == 9600, f'{ll["end_ms"]-ll["start_ms"]}ms')
check("字幕时间按成片顺序累计且无重叠",
      all(lines[i]["end_ms"] <= lines[i+1]["start_ms"] for i in range(len(lines)-1)))

# ---------- 汇总 ----------
print("\n" + "=" * 72)
passed = sum(1 for r in RESULTS if r["pass"])
print(f"结果：{passed}/{len(RESULTS)} 项通过")
print("=" * 72)
out = Path(__file__).parent / "test_result_stage7.json"
out.write_text(json.dumps({"stage": 7, "total": len(RESULTS), "passed": passed,
                           "results": RESULTS,
                           "outputs": {"final": str(outD)}},
                          ensure_ascii=False, indent=2), encoding="utf-8")
print("测试结果已写入", out)
if passed != len(RESULTS):
    sys.exit(1)
