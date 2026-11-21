# -*- coding: utf-8 -*-
"""阶段二自动化测试：真实素材的镜头切分 + 候选片段 + 时间修正 + 重复检测。

运行： .venv\\Scripts\\python.exe tests\\test_stage2.py
结果： 控制台 + tests\\test_result_stage2.json
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, db as dbmod, media
from app.core import scene_detector, duplicate_detector

BASE = Path.home() / "Desktop" / "T26单抽视频"
S01 = BASE / "视屏素材01"
F_ALLDETAIL = S01 / "1" / "IMG_7520整体+细节.MOV"
F_COLOR = S01 / "3" / "IMG_7530三色灯切换.MOV"
F_DRAWER = S01 / "3" / "IMG_7524开关抽屉.MOV"
F_LAMP = S01 / "4" / "IMG_7540旋转灯头7-11.MOV"

results = []


def record(name, inputs, steps, expected, actual, passed, reason=""):
    results.append({
        "测试项目": name, "输入素材": inputs, "执行步骤": steps,
        "预期结果": expected, "实际结果": actual,
        "是否通过": "通过" if passed else "未通过", "失败原因": reason,
    })
    print(f"{'✅' if passed else '❌'} {name}: {actual}")


def main():
    print("=" * 60)
    print("阶段二自动化测试 — 真实素材镜头切分")
    print("=" * 60)

    # --- 测试1：一个视频拆成多个镜头（非等分、非按文件） ---
    r = scene_detector.analyze_video(str(F_ALLDETAIL))
    shots = r["shots"]
    durs = [s["end_ms"] - s["start_ms"] for s in shots]
    non_equal = len(set([d // 100 for d in durs])) > 1  # 时长不全相等=非等分
    record("一个视频拆多镜头", F_ALLDETAIL.name,
           "逐帧采样+多信号峰值检测镜头边界",
           "拆出≥2个镜头，且不是等分",
           f"拆出 {len(shots)} 个镜头，各段时长(秒)={[round(d/1000,1) for d in durs]}",
           len(shots) >= 2 and non_equal)

    # 边界可解释性
    has_reason = all(b.get("reason") for b in r["boundaries"])
    record("切点可解释", F_ALLDETAIL.name,
           "检查每个切点的触发原因",
           "每个切点记录原因与置信度",
           f"{len(r['boundaries'])} 个切点均有原因={has_reason}", has_reason)

    # --- 测试2：灯光/色温变化被标记，不冒充确定切镜 ---
    rc = scene_detector.analyze_video(str(F_COLOR))
    low_conf = [b for b in rc["boundaries"] if b["confidence"] < 0.5]
    record("灯光变化标记核验", F_COLOR.name,
           "分析三色温素材，检查色温变化是否被低置信度标记",
           "色温类变化被标记低置信度/需核验，而非当作确定场景切换",
           f"切点 {len(rc['boundaries'])} 个，其中低置信度(需核验) {len(low_conf)} 个；"
           f"灯光事件 {len(rc['light_events'])} 个",
           len(rc["light_events"]) > 0 or len(low_conf) > 0,
           "" if (len(rc["light_events"]) > 0 or len(low_conf) > 0)
           else "未标记任何灯光变化，可能误判为纯场景切换")

    # --- 测试3：抽屉/灯头素材能切分 ---
    rd = scene_detector.analyze_video(str(F_DRAWER))
    rl = scene_detector.analyze_video(str(F_LAMP))
    record("多类动作素材切分", f"{F_DRAWER.name}, {F_LAMP.name}",
           "分别对抽屉与灯头素材做切镜",
           "两类素材都能拆出候选镜头",
           f"抽屉 {len(rd['shots'])} 段，灯头 {len(rl['shots'])} 段",
           len(rd["shots"]) >= 2 and len(rl["shots"]) >= 2)

    # --- 测试4：候选片段保存到数据库 + 时间修正 ---
    tdb = config.DB_DIR / "_test_stage2.db"
    if tdb.exists():
        tdb.unlink()
    db = dbmod.ProjectDB(str(tdb))
    db.set_project_name("阶段二测试")
    aid = db.add_asset({"path": str(F_ALLDETAIL), "filename": F_ALLDETAIL.name,
                        "folder": str(F_ALLDETAIL.parent), "decode_ok": 1,
                        "duration_ms": r["duration_ms"]})
    kf_map = {}
    for shot in r["shots"]:
        kf_map[shot["index"]] = []  # 测试里不逐个抽帧，真实运行由 AnalyzeWorker 完成
    db.save_scene_analysis(aid, r, kf_map)
    clips = db.get_clips_by_asset(aid)
    saved_ok = len(clips) == len(shots)

    first = clips[0]
    db.update_clip(first["id"], start_ms=1500, end_ms=4500, analysis_status="已人工修正")
    fixed = next(c for c in db.get_clips_by_asset(aid) if c["id"] == first["id"])
    fix_ok = (fixed["start_ms"] == 1500 and fixed["end_ms"] == 4500
              and fixed["analysis_status"] == "已人工修正")
    record("候选片段保存与时间修正", F_ALLDETAIL.name,
           "保存镜头切分结果→修改某片段起止时间→重读",
           "片段数=镜头数，时间修正被持久化",
           f"保存 {len(clips)} 个片段(应={len(shots)})，时间修正持久化={fix_ok}",
           saved_ok and fix_ok)

    # --- 测试5：重新分析只影响本素材，不动其它素材片段 ---
    aid2 = db.add_asset({"path": str(F_COLOR), "filename": F_COLOR.name,
                         "folder": str(F_COLOR.parent), "decode_ok": 1,
                         "duration_ms": rc["duration_ms"]})
    db.save_scene_analysis(aid2, rc, {})
    before = db.get_clips_by_asset(aid)  # 第一条素材的片段
    # 重新分析第二条素材
    db.save_scene_analysis(aid2, rc, {})
    after = db.get_clips_by_asset(aid)
    unchanged = (len(before) == len(after) and
                 all((b["id"], b["start_ms"], b["end_ms"]) ==
                     (a["id"], a["start_ms"], a["end_ms"]) for b, a in zip(before, after)))
    record("单素材重分析不影响其它", F_ALLDETAIL.name + " + " + F_COLOR.name,
           "分析两条素材后，重分析第二条，检查第一条片段是否变化",
           "第一条素材的片段ID与时间完全不变",
           f"第一条片段数 {len(before)}→{len(after)}，保持不变={unchanged}", unchanged)

    # --- 测试6：重复素材检测（MD5） ---
    import shutil, tempfile
    tmp = Path(tempfile.gettempdir()) / "stage2_copy_front.MOV"
    shutil.copy2(str(F_ALLDETAIL), str(tmp))
    assets = [
        {"path": str(F_ALLDETAIL), "filename": F_ALLDETAIL.name},
        {"path": str(tmp), "filename": "改名副本.MOV"},
    ]
    t0 = time.time()
    groups = duplicate_detector.detect(assets)
    exact = groups["exact_groups"]
    exact_ok = len(exact) == 1 and len(exact[0]) == 2
    record("重复素材检测", F_ALLDETAIL.name + " + 改名副本",
           "MD5+感知哈希检测重复",
           "识别为1组完全重复，原件均保留",
           f"完全重复 {len(exact)} 组，耗时 {time.time()-t0:.1f}s，"
           f"原件保留={F_ALLDETAIL.exists() and tmp.exists()}",
           exact_ok and F_ALLDETAIL.exists())
    if tmp.exists():
        tmp.unlink()

    # --- 测试7：项目关闭重开，分析结果仍在 ---
    del db
    db2 = dbmod.ProjectDB(str(tdb))
    clips2 = db2.get_clips()
    groups2 = db2.get_duplicate_groups()
    record("分析结果持久化", str(tdb),
           "关闭数据库后重开，读取候选片段",
           "镜头片段仍在",
           f"重开后候选片段 {len(clips2)} 个", len(clips2) == len(r["shots"]) + len(rc["shots"]))

    summary = {
        "测试时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "总项数": len(results),
        "通过数": sum(1 for x in results if x["是否通过"] == "通过"),
        "未通过数": sum(1 for x in results if x["是否通过"] != "通过"),
        "明细": results,
    }
    out = Path(__file__).parent / "test_result_stage2.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + "=" * 60)
    print(f"结果：{summary['通过数']}/{summary['总项数']} 通过，已写入 {out}")
    print("=" * 60)
    return 0 if summary["未通过数"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
