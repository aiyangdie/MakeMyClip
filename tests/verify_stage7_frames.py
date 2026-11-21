# -*- coding: utf-8 -*-
"""只读核验阶段七成片：抽关键帧拼联络表，人工确认节奏/截短/补足/联动画面。"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import media

OUT = ROOT / "cache" / "verify"
OUT.mkdir(parents=True, exist_ok=True)

d = ROOT / "exports" / "阶段七_淘宝节奏成片.mp4"
info = media.probe(str(d))
dur = info["duration_ms"] / 1000
print(f"成片 {dur:.1f}s {info['width']}x{info['height']}")

# 整片概览：每 4 秒一帧（27s -> 7帧）
vf = "fps=0.25,scale=300:-2,tile=7x1:padding=4:margin=6:color=white"
out = OUT / "D7_overview.jpg"
r = media._run(["-y", "-i", str(d), "-vf", vf, "-frames:v", "1", "-q:v", "3", str(out)], timeout=120)
print("overview:", out.exists(), "rc", r.returncode)

# 联动镜头区间：时间线顺序 整体4 + 台面2.5 + 抽屉5 + 灯头4 -> 联动从约14.4s起，9.6s 长
vf2 = "fps=1.25,scale=300:-2,tile=6x2:padding=4:margin=6:color=white"
out2 = OUT / "D7_linked.jpg"
r2 = media._run(["-y", "-ss", "14.0", "-i", str(d), "-t", "10",
                 "-vf", vf2, "-frames:v", "1", "-q:v", "3", str(out2)], timeout=120)
print("linked sheet:", out2.exists(), "rc", r2.returncode)
print("dir:", OUT)
