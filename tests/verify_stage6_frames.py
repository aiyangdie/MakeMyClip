# -*- coding: utf-8 -*-
"""只读核验阶段六成片：抽关键帧拼联络表，人工确认叠化/停留/联动画面。"""
import sys, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import media

OUT = ROOT / "cache" / "verify"
OUT.mkdir(parents=True, exist_ok=True)

def sheet(src, name, t_list, cols, scale=300):
    frames = []
    for i, t in enumerate(t_list):
        p = OUT / f"{name}_{i:02d}_{int(t*10)}.jpg"
        media._run(["-y", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
                    "-vf", f"scale={scale}:-2", "-q:v", "3", str(p)], timeout=90)
        if p.exists():
            frames.append(p)
    return frames

# 用 ffmpeg 把联动镜头那一段(约在成片中的某个位置)连续抽帧
# C版成片总 51.6s；联动镜头是第9个镜头，前面8个镜头约 39s 左右开始
c = ROOT / "exports" / "阶段六_C_叠化停留按钮联动.mp4"
print("C exists:", c.exists())

# 联动镜头内部：从按下到灯变，抽 12 帧看衔接
vf = "fps=1,scale=300:-2,tile=4x3:padding=4:margin=6:color=white"
out = OUT / "C_linked_sequence.jpg"
r = media._run(["-y", "-ss", "38", "-i", str(c), "-t", "13",
                "-vf", vf, "-frames:v", "1", "-q:v", "3", str(out)], timeout=120)
print("sequence sheet:", out.exists(), "rc", r.returncode)

# 整片概览：每 4 秒一帧
vf2 = "fps=0.25,scale=300:-2,tile=5x3:padding=4:margin=6:color=white"
out2 = OUT / "C_overview.jpg"
r2 = media._run(["-y", "-i", str(c), "-vf", vf2, "-frames:v", "1",
                 "-q:v", "3", str(out2)], timeout=120)
print("overview sheet:", out2.exists(), "rc", r2.returncode)
print("dir:", OUT)
