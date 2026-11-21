# -*- coding: utf-8 -*-
"""只读抽帧核验第二轮：已命名素材 + 灯杆类素材加密抽帧（写入 cache/verify，不碰原片）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import media  # noqa: E402

BASE = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01"
OUT = Path(__file__).resolve().parent.parent / "cache" / "verify"
OUT.mkdir(parents=True, exist_ok=True)

NAMED = [
    BASE / "1" / "IMG_7519整体.MOV",
    BASE / "1" / "IMG_7520整体+细节.MOV",
    BASE / "1" / "IMG_7521台面横扫.MOV",
    BASE / "1" / "IMG_7522正面.MOV",
    BASE / "1" / "IMG_7523侧面转正整体.MOV",
    BASE / "3" / "IMG_7524开关抽屉.MOV",
    BASE / "3" / "IMG_7530三色灯切换.MOV",
    BASE / "4" / "IMG_7540旋转灯头7-11.MOV",
]
# 灯杆类加密：每 0.8 秒 1 帧（重点看灯杆高度有没有变化）
POLE = [
    BASE / "4" / "IMG_7535.MOV",
    BASE / "4" / "IMG_7537.MOV",
    BASE / "4" / "IMG_7541.MOV",
    BASE / "4" / "IMG_7542.MOV",
]


def sheet(f, name, n, cols, rows, scale=380):
    dur = media.probe(str(f)).get("duration_ms", 0) / 1000.0
    ts = [(i + 0.5) * dur / n for i in range(n)]
    vf = ("select='" + "+".join(f"gte(t\\,{t:.2f})" for t in ts) +
          f"',scale={scale}:-2,tile={cols}x{rows}:padding=6:margin=8:color=white")
    r = media._run(["-y", "-i", str(f), "-vf", vf, "-frames:v", "1",
                    "-q:v", "3", str(OUT / name)], timeout=240)
    print(name, "rc=", r.returncode, f"dur={dur:.1f}s")


for f in NAMED:
    sheet(f, f"identify_{f.stem}.jpg", 8, 4, 2)
for f in POLE:
    dur = media.probe(str(f)).get("duration_ms", 0) / 1000.0
    n = min(14, max(8, int(dur / 0.8)))
    sheet(f, f"pole_{f.stem}.jpg", n, 4, 4, 300)
print("done ->", OUT)
