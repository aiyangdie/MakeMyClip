# -*- coding: utf-8 -*-
"""只读分析参考主图视频：
1) 均匀抽帧 -> 画面概览、字幕带、全幅单帧（读烧录字幕与排版）
2) 音频静音/停顿检测 -> 判断配音节奏、是否铺背景音乐
原视频一个字节都不改动；输出只写 cache/verify/ref/。
仅依赖 cv2 + numpy（项目已装）。
"""
import sys
import math
import re
from pathlib import Path
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import media

SRC = r"C:\Users\Administrator\Desktop\店透视_仅主图视频_ID1099472190406_20261119 - 副本\主图视频_1.mp4"
OUT = Path("cache/verify/ref")
OUT.mkdir(parents=True, exist_ok=True)

cap = cv2.VideoCapture(SRC)
fps = cap.get(cv2.CAP_PROP_FPS)
n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
dur = n / fps if fps else 0
print("fps", fps, "frames", n, "dur_s", round(dur, 2))


def grab(t):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, fr = cap.read()
    return fr if ok else None


def sheet(name, times, cell_w, cell_h, crop=None, cols=6):
    rows = math.ceil(len(times) / cols)
    W = cols * (cell_w + 8) + 8
    H = rows * (cell_h + 8) + 8
    canvas = np.full((H, W, 3), 255, np.uint8)
    for i, t in enumerate(times):
        fr = grab(t)
        if fr is None:
            continue
        if crop:
            x0, y0, x1, y1 = crop
            fr = fr[y0:y1, x0:x1]
        fr = cv2.resize(fr, (cell_w, cell_h))
        x = 8 + (i % cols) * (cell_w + 8)
        y = 8 + (i // cols) * (cell_h + 8)
        canvas[y:y + cell_h, x:x + cell_w] = fr
        cv2.putText(canvas, f"{t}s", (x + 5, y + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
    cv2.imwrite(str(OUT / name), canvas, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("saved", name, (W, H))


# 1) 画面概览：每 2 秒一帧（1s~51s），26 格
ts = [1 + i * 2 for i in range(26)]
sheet("ref_overview.jpg", ts, 200, 267, cols=6)

# 2) 字幕带：底部区域裁剪放大，逐格读字幕文字
sheet("ref_sub_bottom.jpg", ts, 320, 195, crop=(0, 520, 720, 960), cols=4)
sheet("ref_sub_tight.jpg", ts, 320, 116, crop=(0, 700, 720, 960), cols=4)

# 3) 全幅单帧：看字幕排版样式（位置/字号/颜色/描边）与画面
for t in [2, 6, 10, 14, 18, 22, 26, 30, 34, 38, 42, 46, 50]:
    fr = grab(t)
    if fr is not None:
        cv2.imwrite(str(OUT / f"ref_full_{t:02d}s.jpg"), fr,
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
print("saved full frames")
cap.release()

# 4) 音频节奏：silencedetect 找静音段
r = media._run(["-hide_banner", "-i", SRC,
                "-af", "silencedetect=noise=-40dB:d=0.3", "-f", "null", "-"],
               timeout=180)
err = r.stderr.decode("utf-8", "ignore") if r.stderr else ""
starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
print("\n--- 音频静音段（-40dB, >=0.3s）---")
print("count:", len(starts))
for i in range(min(len(starts), 40)):
    e = ends[i] if i < len(ends) else None
    print(f"  {starts[i]:6.2f}s -> {e if e is not None else '...'}")
if not starts:
    print("  （几乎无静音：可能全程铺了背景音乐/底噪，或配音连续）")
print("OUT:", OUT.resolve())
