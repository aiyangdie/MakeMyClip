# -*- coding: utf-8 -*-
"""第一阶段自动化测试：用真实素材验证数据层与解码，不依赖人工点界面。

运行： .venv\\Scripts\\python.exe tests\\test_stage1.py
结果： 打印到控制台，并写入 tests\\test_result.json
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QEventLoop

from app import config, db as dbmod, media
from app.ui.player import VideoPlayer

# 真实素材目录
SOURCE_01 = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01"
SOURCE_02 = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材02"
MAIN_VIDEO = Path.home() / "Desktop" / "店透视_仅主图视频_ID1099472190406_20261119 - 副本" / "主图视频_1.mp4"

results = []


def record(name, inputs, steps, expected, actual, passed, reason=""):
    results.append({
        "测试项目": name, "输入素材": inputs, "执行步骤": steps,
        "预期结果": expected, "实际结果": actual,
        "是否通过": "通过" if passed else "未通过", "失败原因": reason,
    })
    flag = "✅" if passed else "❌"
    print(f"{flag} {name}: {actual}")


def collect_videos():
    files = []
    for d in (SOURCE_01, SOURCE_02):
        if d.exists():
            files += sorted(p for p in d.rglob("*") if p.suffix.lower() in config.VIDEO_EXTS)
    return files


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    print("=" * 60)
    print("第一阶段自动化测试 — 真实素材")
    print("=" * 60)

    # --- 测试1：素材发现 ---
    videos = collect_videos()
    record("真实素材发现", str(SOURCE_01) + " + " + str(SOURCE_02),
           "递归扫描两个素材文件夹", "找到 35 条 MOV",
           f"找到 {len(videos)} 条", len(videos) == 35,
           "" if len(videos) == 35 else "数量与预期 35 不符")

    if MAIN_VIDEO.exists():
        record("主图视频存在", str(MAIN_VIDEO), "检查文件存在", "存在",
               f"存在，{MAIN_VIDEO.stat().st_size} 字节", True)
    else:
        record("主图视频存在", str(MAIN_VIDEO), "检查文件存在", "存在",
               "不存在", False, "主图视频_1.mp4 未找到")

    # --- 测试2：逐条元数据探测（真实测量，不编造数字） ---
    t0 = time.time()
    probed = []
    decode_ok_count = 0
    total_duration = 0
    for p in videos:
        info = media.probe(str(p))
        probed.append(info)
        if info["decode_ok"]:
            decode_ok_count += 1
            total_duration += info["duration_ms"]
    elapsed = time.time() - t0
    record("批量元数据探测", f"{len(videos)} 条真实 MOV",
           "逐条读取时长/分辨率/帧率/音轨并做解码检测",
           "每条都有元数据，解码失败被记录而非崩溃",
           f"成功读元数据 {len(probed)} 条，解码正常 {decode_ok_count} 条，"
           f"总时长约 {total_duration/60000:.1f} 分钟，耗时 {elapsed:.1f}s",
           len(probed) == len(videos) and decode_ok_count > 0)

    # 打印几条实际元数据作为证据
    print("\n--- 抽样元数据（真实读取） ---")
    for info in probed[:5]:
        print(f"  {info['filename']}: {media.format_duration(info['duration_ms'])}, "
              f"{info['width']}x{info['height']}, {info['fps']:.1f}fps, "
              f"音轨={'有' if info['has_audio'] else '无'}, 解码={'OK' if info['decode_ok'] else 'FAIL'}")
    print("--- 抽样结束 ---\n")

    # --- 测试3：缩略图生成 ---
    thumb_ok = 0
    for info in probed:
        if info["decode_ok"]:
            tp = media.make_thumb(info["path"], info["duration_ms"])
            if tp and Path(tp).exists():
                thumb_ok += 1
    record("缩略图生成", f"{decode_ok_count} 条可解码素材",
           "每条抽取一帧生成 JPG", "可解码素材均生成缩略图",
           f"生成 {thumb_ok}/{decode_ok_count} 张", thumb_ok == decode_ok_count)

    # --- 测试3b：关键帧抽取（阶段一验收项） ---
    kf_target = next((i for i in probed if i["decode_ok"]), None)
    kfs = []
    if kf_target:
        kfs = media.extract_keyframes(kf_target["path"], kf_target["duration_ms"])
        kf_files_ok = all(Path(k["path"]).exists() for k in kfs)
    else:
        kf_files_ok = False
    record("关键帧抽取", kf_target["filename"] if kf_target else "无",
           "按时间间隔从真实视频抽取关键帧序列",
           "抽出多张关键帧且文件存在",
           f"抽出 {len(kfs)} 张，文件均存在={'是' if kf_files_ok else '否'}",
           len(kfs) >= 2 and kf_files_ok)

    # --- 测试4：中文路径代理（播放器能打开） ---
    player = VideoPlayer()
    target = next((i for i in probed if i["decode_ok"] and "整体" in i["filename"]), None) or \
             next((i for i in probed if i["decode_ok"]), None)
    played = False
    got_frame = False
    frame_holder = {}
    if target:
        player.frame_ready.connect(lambda img: frame_holder.setdefault("img", img))
        played = player.open(target["path"])
        if played:
            # 等一帧解码（最多 3 秒）
            loop = QEventLoop()
            QTimer.singleShot(1500, loop.quit)
            loop.exec()
            got_frame = "img" in frame_holder
            player.pause()
    record("播放器打开真实素材", target["filename"] if target else "无",
           "用中文路径素材打开播放器并解码一帧",
           "播放器成功打开并拿到画面帧",
           f"打开={'成功' if played else '失败'}, 解码到帧={'是' if got_frame else '否'}",
           played and got_frame)

    # --- 测试5：项目保存 + 关闭 + 重新打开 ---
    test_db_path = config.DB_DIR / "_test_stage1.db"
    if test_db_path.exists():
        test_db_path.unlink()
    db1 = dbmod.ProjectDB(str(test_db_path))
    db1.set_project_name("自动化测试项目")
    db1.init_storyboards(config.DEFAULT_STORYBOARD_TEMPLATE)
    for info in probed[:3]:
        db1.add_asset(info)
    sb = db1.get_storyboards()[0]
    db1.update_storyboard(sb["id"], status="已找到候选", note="测试备注", locked=1)
    clip_id = db1.add_clip({
        "storyboard_id": sb["id"], "asset_id": 1, "start_ms": 0, "end_ms": 3000,
        "primary_tag": "overall", "confidence": 0.0,
        "score_text": "第一阶段未做AI评分", "recommend_reason": "测试用",
        "potential_issue": "", "verify_state": "待核验", "source": "manual",
    })
    task_id = db1.add_task("导入素材", input_file="3 个文件")
    db1.finish_task(task_id, "成功", "")
    del db1  # 模拟关闭

    # 重新打开
    db2 = dbmod.ProjectDB(str(test_db_path))
    meta = db2.get_meta()
    assets2 = db2.get_assets()
    sbs2 = db2.get_storyboards()
    clips2 = db2.get_clips()
    tasks2 = db2.get_tasks()
    ok = (meta.get("name") == "自动化测试项目" and len(assets2) == 3
          and len(sbs2) == 12 and sbs2[0]["status"] == "已找到候选"
          and sbs2[0]["locked"] == 1 and len(clips2) == 1 and len(tasks2) == 1)
    record("项目保存与重新打开", str(test_db_path),
           "写入项目/3条素材/12分镜/1候选/1任务 → 关闭 → 重新打开读取",
           "所有数据完整保留",
           f"项目名={meta.get('name')}, 素材={len(assets2)}, 分镜={len(sbs2)}, "
           f"候选={len(clips2)}, 任务={len(tasks2)}", ok)

    # --- 测试6：素材重新定位 ---
    if assets2:
        old = assets2[0]
        db2.update_asset_path(old["id"], old["path"] + ".relocated")
        new = db2.get_asset(old["id"])
        record("素材重新定位", old["filename"],
               "修改素材路径指向新位置", "路径被更新且错误标记清除",
               f"新路径后缀={Path(new['path']).suffix}",
               new["path"].endswith(".relocated"))

    summary = {
        "测试时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "总项数": len(results),
        "通过数": sum(1 for r in results if r["是否通过"] == "通过"),
        "未通过数": sum(1 for r in results if r["是否通过"] != "通过"),
        "明细": results,
    }
    out = Path(__file__).parent / "test_result.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + "=" * 60)
    print(f"结果：{summary['通过数']}/{summary['总项数']} 通过，结果已写入 {out}")
    print("=" * 60)
    return 0 if summary["未通过数"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
