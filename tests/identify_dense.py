# -*- coding: utf-8 -*-
"""只读加密抽帧：长素材找拉手/柜脚/触摸/伸缩特写段（写入 cache/verify，不碰原片）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import media  # noqa: E402

B1 = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01"
B2 = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材02"
OUT = Path(__file__).resolve().parent.parent / "cache" / "verify"

LONG = [
    B2 / "5" / "IMG_7546.MOV",   # 42.1s
    B2 / "5" / "IMG_7544.MOV",   # 21.9s 灯杆锁扣
    B2 / "5" / "IMG_7545.MOV",   # 22.9s 手拧锁扣
    B2 / "7" / "IMG_7577.MOV",   # 25.5s
    B2 / "7" / "IMG_7579.MOV",   # 36.5s
    B2 / "6" / "IMG_7564.MOV",
    B2 / "6" / "IMG_7565.MOV",
    B1 / "4" / "IMG_7540旋转灯头7-11.MOV",
]

for f in LONG:
    dur = media.probe(str(f)).get("duration_ms", 0) / 1000.0
    n = min(24, max(12, int(dur / 2.0)))
    cols = 6
    rows = (n + cols - 1) // cols
    n = cols * rows
    ts = [(i + 0.5) * dur / n for i in range(n)]
    name = f"dense_{f.stem}.jpg"
    vf = ("select='" + "+".join(f"gte(t\\,{t:.2f})" for t in ts) +
          f"',scale=260:-2,tile={cols}x{rows}:padding=4:margin=6:color=white")
    r = media._run(["-y", "-i", str(f), "-vf", vf, "-frames:v", "1",
                    "-q:v", "3", str(OUT / name)], timeout=300)
    print(name, "rc=", r.returncode, f"dur={dur:.1f}s frames={n}")
print("done")
