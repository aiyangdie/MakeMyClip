# -*- coding: utf-8 -*-
"""只读抽帧核验第三轮：视屏素材02 全部15条（写入 cache/verify，不碰原片）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import media  # noqa: E402

BASE = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材02"
OUT = Path(__file__).resolve().parent.parent / "cache" / "verify"
OUT.mkdir(parents=True, exist_ok=True)

FILES = sorted(BASE.rglob("*.MOV"))

for f in FILES:
    dur = media.probe(str(f)).get("duration_ms", 0) / 1000.0
    n = 8
    ts = [(i + 0.5) * dur / n for i in range(n)]
    name = f"id02_{f.stem}.jpg"
    vf = ("select='" + "+".join(f"gte(t\\,{t:.2f})" for t in ts) +
          "',scale=380:-2,tile=4x2:padding=6:margin=8:color=white")
    r = media._run(["-y", "-i", str(f), "-vf", vf, "-frames:v", "1",
                    "-q:v", "3", str(OUT / name)], timeout=240)
    print(name, "rc=", r.returncode, f"dur={dur:.1f}s")
print("total", len(FILES), "->", OUT)
