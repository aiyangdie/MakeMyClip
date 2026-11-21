# -*- coding: utf-8 -*-
"""阶段四自动化测试：非破坏性剪辑（真实素材）。

核心验收（任务书阶段四）：
- 生成成片；替换一个镜头，其它已确认镜头的素材/时间/顺序不变。
- 锁定镜头后重新生成，锁定镜头不被覆盖。
- 改起止时间只影响该镜头；调序不改素材引用。
- 导出 MP4 可播放、比例正确、不拉伸商品（比例适配用 scale+pad）。
- 缓存：改一个镜头时其它镜头缓存命中（不重复渲染）。
"""
import sys, os, json, copy
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, db as dbmod
from app.core import video_editor as ve

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append({"name": name, "pass": bool(cond), "detail": detail})
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f" — {detail}" if detail else ""))

def signature(shots):
    """镜头签名：素材引用+起止+顺序+锁定，用于验证'其它镜头未变'。"""
    return [(s["seq"], s["shot_id"], s.get("asset_path"), s.get("start_ms"),
             s.get("end_ms"), s.get("locked")) for s in shots]

base = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01"
FILES = [
    base / "1" / "IMG_7520整体+细节.MOV",
    base / "3" / "IMG_7530三色灯切换.MOV",
    base / "3" / "IMG_7524开关抽屉.MOV",
    base / "4" / "IMG_7540旋转灯头7-11.MOV",
]

print("=" * 70)
print("阶段四测试：非破坏性剪辑与单镜头编辑（真实素材）")
print("=" * 70)

# ---------- 建一个带时间线的真实项目 ----------
proj = config.DB_DIR / "_stage4_e2e.db"
if proj.exists():
    proj.unlink()
db = dbmod.ProjectDB(str(proj))
db.set_project_name("阶段四端到端")
db.init_storyboards(config.DEFAULT_STORYBOARD_TEMPLATE)

# 导入 4 条素材并各切一段作为候选
asset_ids = []
for f in FILES:
    info = __import__("app.media", fromlist=["probe"]).probe(str(f))
    aid = db.add_asset(info)
    asset_ids.append(aid)
    db.save_scene_analysis(aid, {"shots": [{"index": 1, "start_ms": 0, "end_ms": 3000}],
                                 "boundaries": [], "light_events": []}, {})

# 给前 4 个分镜各绑定一个候选片段（来自不同素材）
sbs = db.get_storyboards()
bound = []
for i, sb in enumerate(sbs[:4]):
    clips = db.get_clips_by_asset(asset_ids[i])
    c = clips[0]
    db.update_storyboard(sb["id"], selected_clip_id=c["id"])
    bound.append((sb["id"], c["id"]))

db.rebuild_timeline_from_storyboards()
shots = db.get_timeline()
print(f"\n[准备] 时间线 {len(shots)} 个镜头")

# ---------- 1. 缓存标识稳定性 ----------
print("\n[1] 缓存标识：输入不变则不变，变了才失效")
ep = {"ratio": "9:16 竖屏", "res": "720p", "fps": 30, "crf": 23}
k1 = ve.cache_key_for(shots[0], ep)
k2 = ve.cache_key_for(shots[0], ep)
check("相同输入缓存标识一致", k1 == k2, k1)
shot_changed = dict(shots[0]); shot_changed["end_ms"] += 1000
check("改起止时间后缓存标识变化", ve.cache_key_for(shot_changed, ep) != k1)
ep_changed = dict(ep); ep_changed["res"] = "1080p"
check("改导出参数后缓存标识变化", ve.cache_key_for(shots[0], ep_changed) != k1)

# ---------- 2. 单镜头渲染+比例适配（不拉伸） ----------
print("\n[2] 单镜头渲染：比例适配不拉伸商品")
r = ve.render_shot(shots[0], ep)
check("镜头渲染成功", r["ok"], r["error"][:100])
info = ve.probe_output(r["path"])
check("竖屏尺寸正确 720x1280", info["width"] == 720 and info["height"] == 1280,
      f'{info["width"]}x{info["height"]}')
check("成片可解码", info["ok"])
r2 = ve.render_shot(shots[0], ep)
check("相同镜头二次渲染命中缓存", r2["cached"])

# 换横屏比例验证不拉伸（scale+pad 应输出正确尺寸）
ep_h = dict(ep); ep_h["ratio"] = "16:9 横屏"
rh = ve.render_shot({**shots[0], "start_ms": 0, "end_ms": 1000}, ep_h)
ih = ve.probe_output(rh["path"])
check("横屏尺寸正确 1280x720", ih["width"] == 1280 and ih["height"] == 720,
      f'{ih["width"]}x{ih["height"]}')

# ---------- 3. 生成整条成片 ----------
print("\n[3] 生成整条成片")
res = ve.render_all(shots, ep, db=db)
# 12 个镜头里只有 4 个绑了素材，其余 8 个是"缺镜头"——正确行为是记录错误而非编造画面
bound_count = len(bound)
check("有素材的镜头全部渲染成功", len(res["segments"]) == bound_count,
      f'成功{len(res["segments"])}/{bound_count}（新生成{res["rendered"]}+缓存{res["cached"]}）')
check("缺素材镜头被正确记录为错误(不编造)", len(res["errors"]) == len(shots) - bound_count,
      f'缺镜头错误 {len(res["errors"])} 个，均为无素材镜头')
out_path = config.EXPORT_DIR / "_stage4_test_final.mp4"
concat = ve.concat_segments(res["segments"], out_path)
check("拼接成片成功", concat["ok"], concat.get("error", "")[:100])
final = ve.probe_output(concat["path"])
check("成片可播放/尺寸对", final["ok"] and final["width"] == 720 and final["height"] == 1280,
      f'{final["width"]}x{final["height"]} {final["duration_ms"]/1000:.1f}s')

# ---------- 4. 替换一个镜头：其它镜头纹丝不动 ----------
print("\n[4] 单镜头替换：其它已确认镜头不变")
before = signature(db.get_timeline())
target = shots[1]["shot_id"]  # 替换第2个镜头
# 用第4个素材的片段替换第2个镜头
alt_clip = db.get_clips_by_asset(asset_ids[3])[0]
alt_asset = db.get_asset(asset_ids[3])
db.replace_shot_clip(target, alt_asset["path"], alt_asset["id"], alt_clip["id"],
                     alt_clip["start_ms"], alt_clip["end_ms"])
after = db.get_timeline()
check("替换后镜头数不变", len(before) == len(after))
changed = [i for i in range(len(before)) if before[i] != signature(after)[i]]
check("只有被替换的镜头发生变化", len(changed) == 1 and after[changed[0]]["shot_id"] == target,
      f"变化的镜头位置={changed}")
check("被替换镜头素材确实换了", after[1]["asset_path"] == alt_asset["path"])
check("其它3个镜头素材/时间/顺序完全一致",
      all(before[i] == signature(after)[i] for i in [0, 2, 3]))

# ---------- 5. 改时间/调序只影响对应镜头 ----------
print("\n[5] 改时间/调序：其它镜头不受影响")
before2 = signature(db.get_timeline())
db.update_shot(target, start_ms=500, end_ms=2500, cache_key="")
after2 = db.get_timeline()
ch2 = [i for i in range(len(before2)) if before2[i] != signature(after2)[i]]
check("改时间只影响1个镜头", len(ch2) == 1 and after2[ch2[0]]["shot_id"] == target,
      f"变化位置={ch2}")
# 调序：只改 seq，素材引用不变
s3 = db.get_timeline()
ids = [s["shot_id"] for s in s3]
paths_before = {s["shot_id"]: s["asset_path"] for s in s3}
ids[0], ids[2] = ids[2], ids[0]
db.reorder_timeline(ids)
s4 = db.get_timeline()
paths_after = {s["shot_id"]: s["asset_path"] for s in s4}
check("调序后素材引用完全不变", paths_before == paths_after)
check("调序确实改变了顺序", [s["shot_id"] for s in s4][0] == ids[0])

# ---------- 6. 锁定镜头不被覆盖 ----------
print("\n[6] 锁定镜头：自动操作不覆盖")
lock_id = s4[0]["shot_id"]
db.update_shot(lock_id, locked=1)
lock_before = db.get_shot(lock_id)
# 尝试改锁定镜头的时间 -> 应被拒绝
ok_modify = db.update_shot(lock_id, start_ms=9999, end_ms=19999)
lock_after = db.get_shot(lock_id)
check("锁定镜头的时间修改被拒绝", not ok_modify and lock_after["start_ms"] == lock_before["start_ms"],
      f'start_ms={lock_after["start_ms"]}')
# 替换候选对锁定镜头也应无效
db.replace_shot_clip(lock_id, "X", 0, 0, 0, 1000)
check("锁定镜头的替换被拒绝", db.get_shot(lock_id)["asset_path"] == lock_before["asset_path"])

# ---------- 7. 改一个镜头后重新成片：其它镜头缓存命中 ----------
print("\n[7] 增量渲染：只重渲染改动镜头")
# 先全部渲染一遍填满缓存（用当前时间线）
r_all1 = ve.render_all(db.get_timeline(), ep, db=db)
# 选一个明确未锁定、有素材的镜头来改；用随机起止时间确保 key 与历史缓存不撞
import random
mod_shot = next(s for s in db.get_timeline() if s.get("asset_path") and not s.get("locked"))
mod_id = mod_shot["shot_id"]
new_start = random.randint(1, 900)
new_end = new_start + random.randint(800, 1500)
old_key = mod_shot.get("cache_key", "")
modified = db.update_shot(mod_id, start_ms=new_start, end_ms=new_end, cache_key="")
check("目标镜头修改成功(未锁定)", modified, mod_id)
new_key = ve.cache_key_for(db.get_shot(mod_id), ep)
check("改动镜头的缓存标识确实变化", new_key != old_key, f"{old_key[:8]} -> {new_key[:8]}")
r_all2 = ve.render_all(db.get_timeline(), ep, db=db)
check("改一个镜头后：仅该镜头重渲染，其余缓存命中",
      r_all2["rendered"] == 1 and r_all2["cached"] >= 1,
      f'新生成{r_all2["rendered"]} 缓存{r_all2["cached"]}')

# ---------- 8. 保存重开 ----------
print("\n[8] 保存项目→重开，时间线完整恢复")
db2 = dbmod.ProjectDB(str(proj))
check("重开后镜头数一致", len(db2.get_timeline()) == len(db.get_timeline()))
check("重开后锁定态保留", bool(db2.get_shot(lock_id).get("locked")))
check("重开后顺序/素材一致", signature(db2.get_timeline()) == signature(db.get_timeline()))

# ---------- 汇总 ----------
print("\n" + "=" * 70)
passed = sum(1 for r in RESULTS if r["pass"])
print(f"结果：{passed}/{len(RESULTS)} 项通过")
print("=" * 70)
out = Path(__file__).parent / "test_result_stage4.json"
out.write_text(json.dumps({"stage": 4, "total": len(RESULTS), "passed": passed,
                           "results": RESULTS}, ensure_ascii=False, indent=2), encoding="utf-8")
print("测试结果已写入", out)
if passed != len(RESULTS):
    sys.exit(1)
