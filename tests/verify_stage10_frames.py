# -*- coding: utf-8 -*-
"""阶段十成片抽帧核验：参考片风格 vs 标准模式回退，逐帧看字幕排版。"""
import sys, os, math
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import media
import cv2, numpy as np

OUT = Path("cache/verify/ref"); OUT.mkdir(parents=True, exist_ok=True)


def sheet(video, name, times, cols=4, crop=None, cw=270, ch=360):
    cap = cv2.VideoCapture(str(video))
    frames = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        if not ok:
            continue
        if crop:
            x0, y0, x1, y1 = crop
            fr = fr[y0:y1, x0:x1]
        fr = cv2.resize(fr, (cw, ch))
        frames.append((t, fr))
    cap.release()
    rows = math.ceil(len(frames) / cols)
    canvas = np.full((rows * (ch + 26) + 8, cols * (cw + 8) + 8, 3), 255, np.uint8)
    for i, (t, fr) in enumerate(frames):
        x = 8 + (i % cols) * (cw + 8)
        y = 8 + (i // cols) * (ch + 26)
        canvas[y:y + ch, x:x + cw] = fr
        cv2.putText(canvas, f"{t:.1f}s", (x + 4, y + ch + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(OUT / name), canvas, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("saved", name)


def single(video, t, name):
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, fr = cap.read()
    cap.release()
    if ok:
        cv2.imwrite(str(OUT / name), fr, [cv2.IMWRITE_JPEG_QUALITY, 92])
        print("saved", name)


badge = Path("exports/阶段十_参考片风格.mp4")
if badge.exists():
    print("=== 参考片风格成片 ===")
    sheet(badge, "F10_final_badge_overview.jpg",
          [1.0, 3.2, 5.2, 7.0, 9.0, 11.5, 13.0, 14.8, 17.2, 19.5, 21.0, 24.0, 28.5], cols=4)
    single(badge, 1.2, "F10_final_title.jpg")   # 开场标题
    single(badge, 6.9, "F10_final_tag.jpg")      # 圆形拉手
    single(badge, 23.0, "F10_final_big.jpg")     # 三色灯光紫底大字
else:
    print("MISSING", badge)

std = Path("exports/阶段十_标准模式回退.mp4")
if std.exists():
    print("=== 标准模式回退成片 ===")
    single(std, 2.0, "F10_final_std.jpg")
else:
    print("MISSING", std)
