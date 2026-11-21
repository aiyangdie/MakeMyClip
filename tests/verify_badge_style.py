# -*- coding: utf-8 -*-
"""阶段十视觉冒烟：把卖点标签字幕烧到阶段九成片，抽帧确认排版效果。
只读原片，输出写 cache/verify/ref/ 与 exports/。
"""
import sys, os
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, db as dbmod, media
from app.core import narration, subtitle, bgm, video_editor
import cv2, numpy as np

proj = config.DB_DIR / "_stage9_full.db"
db = dbmod.ProjectDB(str(proj))
shots = [s for s in db.get_timeline() if (s.get("asset_path") or "").strip() or s.get("sub_segments")]
info = {"name": "带灯床头柜", "color": "白色", "material": ""}

# 1) 卖点标签文案
res = narration.build_selling_lines(shots, info)
print("lines:", len(res["lines"]))
for ln in res["lines"]:
    print(f'  {ln["start_ms"]/1000:5.2f}-{ln["end_ms"]/1000:5.2f}s  [{ln["kind"]:5}] {ln["text"]}')
print("forbidden claims:", narration.validate_selling_labels(res["lines"]))

# 2) 生成 ASS（按成片真实尺寸 720x960）
silent = config.EXPORT_DIR / "阶段九_全镜头补齐.mp4"
p = media.probe(str(silent))
print("silent:", p["width"], "x", p["height"], p["duration_ms"] / 1000, "s")
work = config.CACHE_DIR / "verify_badge"
work.mkdir(parents=True, exist_ok=True)
ass = work / "badge.ass"
subtitle.build_ass_badge(res["lines"], ass, {"play_w": p["width"], "play_h": p["height"]})
print("ASS head:")
print("\n".join(ass.read_text(encoding="utf-8-sig").splitlines()[:16]))

# 3) 烧字幕到成片（用 burn_subtitles 的 preset 路径）
srt = work / "badge.srt"
subtitle.build_srt(res["lines"], srt)
burned = work / "badge_burned.mp4"
r = subtitle.burn_subtitles(str(silent), str(srt), str(burned),
                            style={"preset": subtitle.BADGE_PRESET,
                                   "lines": res["lines"]}, enabled=True)
print("burn:", r)

# 4) 抽帧：每隔约 2.3 秒一帧，看字幕排版；再放大几张关键帧
if r["ok"]:
    src = str(burned)
    cap = cv2.VideoCapture(src)
    dur = p["duration_ms"] / 1000
    times = [1.2 + i * 2.3 for i in range(13)]
    cells, labels = [], []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        if not ok:
            continue
        fr = cv2.resize(fr, (216, 288))
        cells.append(fr)
        labels.append(t)
    cap.release()
    import math
    cols = 5
    rows = math.ceil(len(cells) / cols)
    canvas = np.full((rows * 300 + 8, cols * 224 + 8, 3), 255, np.uint8)
    for i, (fr, t) in enumerate(zip(cells, labels)):
        x = 8 + (i % cols) * 224
        y = 8 + (i // cols) * 300
        canvas[y:y + 288, x:x + 216] = fr
        cv2.putText(canvas, f"{t:.1f}s", (x + 4, y + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
    out = Path("cache/verify/ref") / "F10_badge_overview.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), canvas, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("overview:", out)

    # 放大 3 张：开场标题、普通卖点、三色灯光大字
    for t, name in [(1.5, "F10_badge_title.jpg"), (8.0, "F10_badge_tag.jpg"), (24.0, "F10_badge_big.jpg")]:
        cap = cv2.VideoCapture(src)
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        cap.release()
        if ok:
            fp = Path("cache/verify/ref") / name
            cv2.imwrite(str(fp), fr, [cv2.IMWRITE_JPEG_QUALITY, 92])
            print("frame:", fp)
