# -*- coding: utf-8 -*-
"""修正版均匀抽帧：用 fps 滤镜按固定时间间隔取样（此前 select+gte 相加会取成开头连续帧）。

对两批共 35 条素材全部重查，长素材每 2 秒一帧、短素材每 0.8 秒一帧，
写入 cache/verify/uniform_*.jpg，原片只读。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import media  # noqa: E402

BASE = Path.home() / "Desktop" / "T26单抽视频"
OUT = ROOT / "cache" / "verify"
OUT.mkdir(parents=True, exist_ok=True)

FILES = sorted((BASE / "视屏素材01").rglob("*.MOV")) + sorted((BASE / "视屏素材02").rglob("*.MOV"))

for f in FILES:
    dur = media.probe(str(f)).get("duration_ms", 0) / 1000.0
    step = 2.0 if dur > 14 else 0.8
    # fps 滤镜按时间间隔均匀取样；tile 最多 30 格
    n = min(30, max(8, int(dur / step)))
    fps = 1.0 / step
    cols, rows = 6, 5
    vf = (f"fps={fps:.4f},scale=250:-2,"
          f"tile={cols}x{rows}:padding=4:margin=6:color=white")
    name = f"uniform_{f.stem}.jpg"
    r = media._run(["-y", "-i", str(f), "-vf", vf, "-frames:v", "1",
                    "-q:v", "3", str(OUT / name)], timeout=300)
    print(name, "rc=", r.returncode, f"dur={dur:.1f}s step={step}s")
print("total", len(FILES))
