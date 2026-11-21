# -*- coding: utf-8 -*-
"""只读抽帧核验：为未命名素材逐条生成联络表（写入 cache/verify，不碰原片）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import media  # noqa: E402

BASE = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01"
OUT = Path(__file__).resolve().parent.parent / "cache" / "verify"
OUT.mkdir(parents=True, exist_ok=True)

FILES = [
    BASE / "2" / "IMG_7532.MOV",
    BASE / "3" / "IMG_7525抽屉细节.MOV",
    BASE / "3" / "IMG_7528.MOV",
    BASE / "3" / "IMG_7531.MOV",
    BASE / "3" / "IMG_7533.MOV",
    BASE / "3" / "IMG_7534.MOV",
    BASE / "4" / "IMG_7535.MOV",
    BASE / "4" / "IMG_7537.MOV",
    BASE / "4" / "IMG_7538.MOV",
    BASE / "4" / "IMG_7539.MOV",
    BASE / "4" / "IMG_7541.MOV",
    BASE / "4" / "IMG_7542.MOV",
]

for f in FILES:
    if not f.exists():
        print("缺文件:", f)
        continue
    dur = media.probe(str(f)).get("duration_ms", 0) / 1000.0
    # 6 帧：10%~85% 均布
    ts = [dur * p for p in (0.10, 0.25, 0.40, 0.55, 0.70, 0.85)]
    name = f"identify_{f.stem}.jpg"
    vf = ("select='" + "+".join(f"gte(t\\,{t:.2f})" for t in ts) +
          "',scale=380:-2,tile=3x2:padding=6:margin=8:color=white")
    r = media._run(["-y", "-i", str(f), "-vf", vf, "-frames:v", "1",
                    "-q:v", "3", str(OUT / name)], timeout=180)
    print(name, "rc=", r.returncode, f"dur={dur:.1f}s")
print("done ->", OUT)
