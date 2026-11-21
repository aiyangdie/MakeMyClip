# -*- coding: utf-8 -*-
"""阶段九：补齐全部缺镜头（用户点名的4个 + 顺带3个），压进淘宝30秒区间，真实导出。

严格约束：
- 在 _stage7_e2e.db 的副本 _stage9_full.db 上操作，原项目不动。
- 每个镜头只 UPDATE 自己那一行；不动任何已确认/锁定镜头。
- 全部素材为 35 条真实素材中逐帧核验过的文件，绝不虚构。
- 原始素材只读；日志由 commands 层记录。
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import commands, config, media  # noqa: E402
from app import db as dbmod              # noqa: E402

B1 = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01"
B2 = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材02"

# 逐帧核验过的真实素材（详见 cache/verify/identify_*.jpg, id02_*.jpg, dense_*.jpg）
P7522 = B1 / "1" / "IMG_7522正面.MOV"          # 金色圆拉手（中景，初版用）
P7528 = B1 / "3" / "IMG_7528.MOV"              # 手握线控实体开关
P7531 = B1 / "3" / "IMG_7531.MOV"              # 亮灯灯罩特写
P7530 = B1 / "3" / "IMG_7530三色灯切换.MOV"    # 按钮+灯变（阶段六已核验）
P7544 = B2 / "5" / "IMG_7544.MOV"              # 灯杆伸缩锁扣结构特写
P7545 = B2 / "5" / "IMG_7545.MOV"              # 手握伸缩锁扣
P7546 = B2 / "5" / "IMG_7546.MOV"              # 【均匀抽帧复查】手拧/拉动灯杆连接节（伸缩调节演示）
P7561 = B2 / "6" / "IMG_7561.MOV"              # 四条黑色柜脚（中景，初版用）
P7562 = B2 / "6" / "IMG_7562.MOV"              # 抽屉拉开、木纹内里
P7577 = B2 / "7" / "IMG_7577.MOV"              # 【复查】双手按压柜面展示柔软质感 + 拉手/柜脚
P7579 = B2 / "7" / "IMG_7579.MOV"              # 【复查】手转金色拉手特写 + 抽屉/柜脚
P7580 = B2 / "7" / "IMG_7580.MOV"              # 手在柜体表面连续轻抚

SRC = config.DB_DIR / "_stage7_e2e.db"
DB = config.DB_DIR / "_stage9_full.db"
shutil.copyfile(SRC, DB)
P = "_stage9_full"
db = dbmod.ProjectDB(str(DB))

results = []


def check(name, ok, note=""):
    results.append({"name": name, "ok": bool(ok), "note": str(note)})
    print(("[PASS] " if ok else "[FAIL] ") + name + (f"  {note}" if note else ""))


# ---------- 1. 素材登记入库（原片只读，只登记路径/时长等元信息） ----------
def imp(path):
    info = media.probe(str(path))
    return db.add_asset({
        "path": str(path), "filename": path.name, "folder": path.parent.name,
        "size_bytes": path.stat().st_size,
        "duration_ms": info.get("duration_ms", 0), "width": info.get("width", 0),
        "height": info.get("height", 0), "fps": info.get("fps", 0),
        "decode_ok": 1 if info.get("decode_ok") else 0,
        "error": info.get("error", ""),
    })


assets = {p.name: (p, imp(p)) for p in
          [P7522, P7528, P7531, P7544, P7545, P7546, P7561, P7562,
           P7577, P7579, P7580]}
check("真实素材全部存在且登记入库",
      all(p.exists() for p, _ in assets.values()) and len(assets) == 11,
      f"{len(assets)} 条（按钮联动素材 P7530 沿用原有）")


def bind(name, path, start_ms, end_ms, target_ms, aid):
    """只动这一个镜头行：绑定真实素材 + 建议时长。"""
    shot = next((s for s in db.get_timeline() if s["name"] == name), None)
    if not shot:
        raise RuntimeError(f"找不到镜头 {name}")
    db.replace_shot_clip(shot["shot_id"], str(path), aid, None, start_ms, end_ms)
    db.update_shot(shot["shot_id"], target_ms=target_ms)
    return shot["shot_id"]


# ---------- 2. 新增分镜「触摸柜面质感」并重建（只插入缺失行） ----------
sb_id = db.add_storyboard("触摸柜面质感")
db.update_storyboard(sb_id, target_ms=2500)
made = db.rebuild_timeline_from_storyboards()
check("新增分镜并只补1行时间线", made == 1, f"新建 {made} 行")
check("触摸柜面质感镜头已在时间线",
      any(s["name"] == "触摸柜面质感" for s in db.get_timeline()))

# ---------- 3. 逐个绑定（真实素材，每个只动自己那行） ----------
# 复查修正：改用均匀抽帧找到的"专门特写"片段（比中景更贴切，仍全是真实画面）
p, a = assets[P7577.name]
bind("触摸柜面质感", p, 12000, 16000, 2500, a)     # 双手按压柜面展示柔软质感
p, a = assets[P7579.name]
bind("拉手特写", p, 27000, 31000, 1800, a)          # 手转金色拉手特写
p, a = assets[P7562.name]
bind("抽屉内部", p, 0, 5000, 2000, a)               # 抽屉内里
p, a = assets[P7579.name]
bind("柜脚和底部", p, 31000, 35000, 1800, a)        # 抽屉/柜脚特写段
p, a = assets[P7531.name]
bind("灯罩细节", p, 0, 4000, 2000, a)               # 灯罩特写
p, a = assets[P7528.name]
bind("实体开关按钮", p, 0, 3500, 1800, a)           # 手握线控开关

# 灯杆伸缩调节：锁扣结构特写 → 手拧/拉动灯杆连接节（两条真实画面，中间短叠化）
p46, a46 = assets[P7546.name]
p44, _ = assets[P7544.name]
sid = bind("灯杆调节", p46, 0, 42100, 2600, a46)
db.set_linked_shot(sid, [
    {"asset_path": str(p44), "start_ms": 2000, "end_ms": 9000, "target_ms": 1200},
    {"asset_path": str(p46), "start_ms": 6000, "end_ms": 14000, "target_ms": 1800},
], name="灯杆伸缩调节")

# 按钮触发三色灯：沿用阶段六核验的两段真实画面，子片段时长压到 2.0s + 4.4s
btn = next(s for s in db.get_timeline() if s["name"] == "按钮触发三色灯")
db.set_linked_shot(btn["shot_id"], [
    {"asset_path": str(P7530), "start_ms": 0, "end_ms": 2000, "target_ms": 2000},
    {"asset_path": str(P7530), "start_ms": 4000, "end_ms": 13000, "target_ms": 4400},
], name="按钮触发三色灯")

# ---------- 4. 排顺序 + 分配建议时长（全补，压进30秒） ----------
order = ["产品整体亮相", "台面材质和边缘", "触摸柜面质感", "拉手特写",
         "抽屉开合", "抽屉内部", "柜脚和底部", "灯杆伸缩调节", "灯头旋转",
         "灯罩细节", "实体开关按钮", "按钮触发三色灯", "整体收尾"]
name2id = {s["name"]: s["shot_id"] for s in db.get_timeline()}
db.reorder_timeline([name2id[n] for n in order])

targets = {
    "产品整体亮相": 3000, "台面材质和边缘": 2000, "触摸柜面质感": 2500,
    "拉手特写": 1800, "抽屉开合": 3500, "抽屉内部": 2000, "柜脚和底部": 1800,
    "灯杆伸缩调节": 2600, "灯头旋转": 3000, "灯罩细节": 2000,
    "实体开关按钮": 1800, "按钮触发三色灯": 6000, "整体收尾": 2500,
}
for s in db.get_timeline():
    db.update_shot(s["shot_id"], target_ms=targets[s["name"]])
db.touch_modified()

tl = db.get_timeline()
check("13个镜头全部有真实素材/联动片段",
      len(tl) == 13 and all(s.get("asset_path") or s.get("sub_segments") for s in tl),
      f"{len(tl)} 行，0 缺失")
check("四个点名镜头均绑定复查后的真实特写",
      next(s for s in tl if s["name"] == "触摸柜面质感")["asset_path"] == str(P7577)
      and next(s for s in tl if s["name"] == "拉手特写")["asset_path"] == str(P7579)
      and next(s for s in tl if s["name"] == "柜脚和底部")["asset_path"] == str(P7579)
      and "IMG_7546" in next(s for s in tl if s["name"] == "灯杆伸缩调节")["sub_segments"])
check("所有绑定素材文件真实存在",
      all(Path(s["asset_path"]).exists() for s in tl if s.get("asset_path")))

# 单镜头独立性：改一个镜头的建议时长，其他行逐一比对未动
snapshot = {s["shot_id"]: (s["asset_path"], s["start_ms"], s["end_ms"], s["target_ms"])
            for s in db.get_timeline()}
one = next(s for s in tl if s["name"] == "灯头旋转")
r = commands.set_shot_target(P, one["shot_id"], 3.2)
other_same = all(
    (s["asset_path"], s["start_ms"], s["end_ms"], s["target_ms"]) ==
    snapshot[s["shot_id"]]
    for s in db.get_timeline() if s["shot_id"] != one["shot_id"])
check("改单镜头建议时长不影响其它12行", r["ok"] and other_same)
db.update_shot(one["shot_id"], target_ms=3000)  # 还原模板节奏

# ---------- 5. 导出（护栏 + 真实渲染） ----------
try:
    commands.export_video(P, "_stage9_guard.mp4", confirm=False)
    check("未确认导出仍被拒绝", False)
except commands.CommandError as e:
    check("未确认导出仍被拒绝", "同意" in str(e))

r = commands.export_video(P, "阶段九_全镜头补齐.mp4", confirm=True,
                          ratio="3:4 竖版", res="720p", fps=30)
check("确认后真实导出成功", r["ok"] and Path(r["output"]).exists(),
      f"{r['duration_s']}s {r['width']}x{r['height']}")
check("成片总长压进淘宝最佳区间(<=30s)", 15 <= r["duration_s"] <= 30,
      f"{r['duration_s']}s")
check("13个镜头全部渲染、0缺失跳过", not r["skipped_missing"],
      f"跳过 {len(r['skipped_missing'])} 个")
check("3:4竖版720x960", r["width"] == 720 and r["height"] == 960)

n_pass = sum(1 for x in results if x["ok"])
out = {"stage": 9, "total": len(results), "pass": n_pass,
       "ok": n_pass == len(results), "results": results,
       "output": r.get("output", ""), "duration_s": r.get("duration_s", 0)}
(ROOT / "tests" / "test_result_stage9.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n阶段九：{n_pass}/{len(results)} 通过")
sys.exit(0 if n_pass == len(results) else 1)
