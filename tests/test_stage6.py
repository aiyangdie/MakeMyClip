# -*- coding: utf-8 -*-
"""阶段六测试：转场自然 / 最短停留 / 按钮联动，且单镜头独立性铁律不破。

真实素材构造时间线，生成三个对比版本：
  A 原样：硬切 + 无停留 + 按钮/灯分开
  B 优化：叠化 + 3.5s 停留
  C 优化+联动：叠化 + 3.5s 停留 + 按钮触发三色灯(一个镜头含两段真实画面)
并验证：
  - 转场只作用于拼接层，改一个镜头的画面不影响其它镜头缓存/内容
  - 最短停留让短片段达到 3.5s
  - 联动镜头在时间线里仍是一行；设置联动只改它自己那一行
  - 联动子片段来自逐帧核验过的真实画面（0-2s 按下 + 4-13s 灯变）
"""
import sys, os, json, copy
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, db as dbmod, media
from app.core import video_editor as ve
from app.core import storyboard_matcher as sm

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append({"name": name, "pass": bool(cond), "detail": detail})
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f" — {detail}" if detail else ""))

def signature(shots):
    return [(s["seq"], s["shot_id"], s.get("asset_path"), s.get("start_ms"),
             s.get("end_ms"), s.get("locked"), s.get("sub_segments", ""))
            for s in shots]

base = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01"
F_WHOLE  = base / "1" / "IMG_7520整体+细节.MOV"
F_LIGHT  = base / "3" / "IMG_7530三色灯切换.MOV"
F_DRAWER = base / "3" / "IMG_7524开关抽屉.MOV"
F_HEAD   = base / "4" / "IMG_7540旋转灯头7-11.MOV"

print("=" * 72)
print("阶段六测试：转场 / 最短停留 / 按钮联动（真实素材）")
print("=" * 72)

# ---------- 0. 模板联动定义校验 ----------
print("\n[0] 分镜模板联动定义")
tpl = sm.load_template()
check("模板含 linked_shots 定义", bool(tpl and tpl.get("linked_shots")))
lk = tpl["linked_shots"][0] if tpl and tpl.get("linked_shots") else {}
check("联动理由声明为真实画面无虚构", "真实画面" in lk.get("reason", ""))
check("联动含按下与变换两个真实子片段",
      len(lk.get("segments", [])) == 2 and
      lk["segments"][0]["end_ms"] == 2000 and lk["segments"][1]["start_ms"] == 4000)

# ---------- 构造真实项目时间线 ----------
proj = config.DB_DIR / "_stage6_e2e.db"
if proj.exists():
    proj.unlink()
db = dbmod.ProjectDB(str(proj))
db.set_project_name("阶段六端到端")
db.init_storyboards(config.DEFAULT_STORYBOARD_TEMPLATE)

asset_paths = {
    "whole": str(F_WHOLE), "light": str(F_LIGHT),
    "drawer": str(F_DRAWER), "head": str(F_HEAD),
}
aids = {}
for k, p in asset_paths.items():
    info = media.probe(p)
    aids[k] = db.add_asset(info)
    db.save_scene_analysis(aids[k], {"shots": [{"index": 1, "start_ms": 0,
                              "end_ms": info.get("duration_ms", 8000)}],
                             "boundaries": [], "light_events": []}, {})

sbs = db.get_storyboards()
by_name = {s["name"]: s for s in sbs}
# 给 5 个分镜绑定真实素材，其中"三色温切换"作为联动镜头的载体
plan = [
    ("产品整体亮相", "whole", 0, 2200),
    ("台面材质和边缘", "whole", 2500, 4000),   # 1.5s 短片段 -> 测最短停留
    ("抽屉开合", "drawer", 0, 3000),
    ("灯头旋转", "head", 8000, 11500),
    ("三色温切换", "light", 4000, 13000),      # 稍后设为联动镜头
]
# 记录每个镜头要用的真实片段路径（元素顺序与 plan 对齐）
plan_paths = []
for name, key, s, e in plan:
    c = db.get_clips_by_asset(aids[key])[0]
    db.update_storyboard(by_name[name]["id"], selected_clip_id=c["id"])
    plan_paths.append(asset_paths[key])
db.rebuild_timeline_from_storyboards()

# 把"台面材质和边缘"真的改成 1.5 秒短镜头，才能验证最短停留补足
timeline = db.get_timeline()
short = next(s for s in timeline if s["name"] == "台面材质和边缘")
db.update_shot(short["shot_id"], start_ms=2500, end_ms=4000)

# 把"三色温切换"镜头设为联动：0-2s 按下 + 4-13s 灯变（真实，来自核验）
# 模板里用 asset_hint（文件名），这里映射成项目里真实的绝对路径
timeline = db.get_timeline()
target = next(s for s in timeline if s["name"] == "三色温切换")
link_subs = []
for seg in lk["segments"]:
    hint = seg.get("asset_hint", "")
    real_path = next((p for p in asset_paths.values() if Path(p).name == hint), asset_paths["light"])
    link_subs.append({"asset_path": real_path,
                      "start_ms": seg["start_ms"], "end_ms": seg["end_ms"],
                      "role": seg.get("role", "")})
db.set_linked_shot(
    target["shot_id"], link_subs, name="按钮触发三色灯")
timeline = db.get_timeline()
print(f"\n[准备] 时间线 {len(timeline)} 镜头；其中联动 1 个")

# ---------- 1. 最短停留 ----------
print("\n[1] 最短停留：短片段补足到 3.5s")
ep_hold = {"ratio": "9:16 竖屏", "res": "720p", "fps": 30, "crf": 23,
           "min_hold_ms": 3500, "transition": "fade", "transition_s": 0.4,
           "sub_transition_s": 0.4}
short_shot = next(s for s in timeline if s["name"] == "台面材质和边缘")
r = ve.render_shot(short_shot, ep_hold)
info = ve.probe_output(r["path"])
check("短镜头(1.5s)渲染成功", r["ok"], r["error"][:80])
check("补足后时长达到约3.5s", 3200 <= info["duration_ms"] <= 3800,
      f'{info["duration_ms"]/1000:.2f}s')
check("仍是竖屏不拉伸", info["width"] == 720 and info["height"] == 1280)

# 停留时间变化 -> cache_key 变化
k0 = ve.cache_key_for(short_shot, {"ratio": "9:16 竖屏", "res": "720p", "fps": 30, "crf": 23})
k1 = ve.cache_key_for(short_shot, ep_hold)
check("改最短停留会改变缓存标识", k0 != k1)

# ---------- 2. 联动镜头渲染 ----------
print("\n[2] 按钮联动：一个镜头含两段真实画面")
linked = next(s for s in timeline if s.get("sub_segments"))
check("联动镜头正确写入 sub_segments", bool(linked["sub_segments"]))
rl = ve.render_linked_shot(linked, ep_hold)
il = ve.probe_output(rl["path"])
check("联动镜头渲染成功", rl["ok"], rl["error"][:120])
# 按下段2s经最短停留补到3.5s + 灯变段9s - 叠化0.4s ≈ 12.1s
check("联动镜头时长≈按下3.5s+灯变9s-叠化0.4s", 11500 <= il["duration_ms"] <= 13000,
      f'{il["duration_ms"]/1000:.2f}s')

# ---------- 3. 三个版本成片 ----------
print("\n[3] 生成三个对比成片")
bound_shots = [s for s in timeline if s.get("asset_path") or s.get("sub_segments")]
print(f"    有画面镜头 {len(bound_shots)} 个")

# A：原样硬切、无停留、无联动（把联动拆回普通镜头=灯变单段）
shots_A = []
for s in bound_shots:
    sa = dict(s)
    if sa.get("sub_segments"):
        sa["sub_segments"] = ""
        sa["start_ms"], sa["end_ms"] = 4000, 13000   # 只有灯变，按钮/灯分开
    shots_A.append(sa)
epA = {"ratio": "9:16 竖屏", "res": "720p", "fps": 30, "crf": 23,
       "transition": "none", "min_hold_ms": 0}
resA = ve.render_all(shots_A, epA)
outA = config.EXPORT_DIR / "阶段六_A_原样硬切.mp4"
ca = ve.concat_segments(resA["segments"], outA, transition="none")
check("A版硬切成片成功", ca["ok"], ca.get("error", "")[:100])

# B：叠化 + 3.5s 停留，无联动
shots_B = []
for s in bound_shots:
    sb = dict(s)
    if sb.get("sub_segments"):
        sb["sub_segments"] = ""
        sb["start_ms"], sb["end_ms"] = 4000, 13000
    shots_B.append(sb)
resB = ve.render_all(shots_B, ep_hold)
outB = config.EXPORT_DIR / "阶段六_B_叠化停留.mp4"
cb = ve.concat_segments(resB["segments"], outB, transition="fade", transition_s=0.4)
check("B版叠化+停留成片成功", cb["ok"], cb.get("error", "")[:100])

# C：叠化 + 停留 + 按钮联动
resC = ve.render_all(bound_shots, ep_hold)
outC = config.EXPORT_DIR / "阶段六_C_叠化停留按钮联动.mp4"
cc = ve.concat_segments(resC["segments"], outC, transition="fade", transition_s=0.4)
check("C版(含按钮联动)成片成功", cc["ok"], cc.get("error", "")[:100])
for tag, out in [("A", outA), ("B", outB), ("C", outC)]:
    p = ve.probe_output(str(out))
    check(f"{tag}版可解码且尺寸正确", p["ok"] and p["width"] == 720 and p["height"] == 1280,
          f'{p["duration_ms"]/1000:.1f}s {p["width"]}x{p["height"]}')

# ---------- 4. 铁律：单镜头独立修改不影响其它镜头 ----------
print("\n[4] 铁律回归：改联动镜头不影响其它镜头")
before = signature(db.get_timeline())
other_ids = [s["shot_id"] for s in db.get_timeline() if not s.get("sub_segments")]
other_before = {sid: db.get_shot(sid) for sid in other_ids}
# 改联动镜头的子片段时间
new_subs = copy.deepcopy(link_subs)
new_subs[1]["end_ms"] = 12000
db.set_linked_shot(target["shot_id"], new_subs, name="按钮触发三色灯")
after = db.get_timeline()
changed = [i for i in range(len(before)) if before[i] != signature(after)[i]]
check("只有联动镜头这一行发生变化",
      len(changed) == 1 and after[changed[0]]["shot_id"] == target["shot_id"],
      f"变化位置={changed}")
check("其它镜头素材/时间/子片段完全不变",
      all(other_before[sid] == db.get_shot(sid) for sid in other_ids))

# 锁定镜头拒绝修改（含联动）
db.update_shot(target["shot_id"], locked=1)
ok_mod = db.set_linked_shot(target["shot_id"], link_subs)
check("锁定后联动镜头也拒绝修改", not ok_mod)

# ---------- 汇总 ----------
print("\n" + "=" * 72)
passed = sum(1 for r in RESULTS if r["pass"])
print(f"结果：{passed}/{len(RESULTS)} 项通过")
print("=" * 72)
out = Path(__file__).parent / "test_result_stage6.json"
out.write_text(json.dumps({"stage": 6, "total": len(RESULTS), "passed": passed,
                           "results": RESULTS,
                           "outputs": {"A": str(outA), "B": str(outB), "C": str(outC)}},
                          ensure_ascii=False, indent=2), encoding="utf-8")
print("测试结果已写入", out)
if passed != len(RESULTS):
    sys.exit(1)
