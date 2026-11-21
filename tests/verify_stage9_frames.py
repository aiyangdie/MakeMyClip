# -*- coding: utf-8 -*-
"""阶段九成片抽帧核验：概览联络表 + 六个重点镜头放大单帧（只读，写入 cache/verify）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import media  # noqa: E402

D = ROOT / "exports" / "阶段九_全镜头补齐.mp4"
OUT = ROOT / "cache" / "verify"
OUT.mkdir(parents=True, exist_ok=True)

# 概览：用 fps 滤镜按每 1.5 秒一帧均匀取样，20 格（5x4）覆盖 30 秒
# （修正：此前 select+gte 相加会退化成"开头连续帧"，导致误判）
vf = ("fps=0.6667,scale=250:-2,"
      "tile=5x4:padding=4:margin=6:color=white")
r = media._run(["-y", "-i", str(D), "-vf", vf, "-frames:v", "1",
                "-q:v", "3", str(OUT / "E9_overview.jpg")], timeout=300)
print("E9_overview.jpg rc=", r.returncode)

# 六个重点镜头放大（按累计时间估算，含叠化重叠）
for t, name in [(5.4, "E9_touch.jpg"), (7.3, "E9_handle.jpg"),
                (11.8, "E9_drawer_in.jpg"), (13.4, "E9_feet.jpg"),
                (15.0, "E9_pole.jpg"), (24.0, "E9_button.jpg")]:
    r = media._run(["-y", "-ss", str(t), "-i", str(D), "-frames:v", "1",
                    "-q:v", "2", str(OUT / name)], timeout=60)
    print(name, "rc=", r.returncode)
print("done ->", OUT)
