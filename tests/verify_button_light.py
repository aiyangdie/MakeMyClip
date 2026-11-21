# -*- coding: utf-8 -*-
"""只读核验：抽 IMG_7530 的画面拼成联络表，判断有无"按按钮+灯变"同框。

不修改、不复制原始素材；只把抽出的图片写到 cache/verify/ 供人工查看。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import media  # noqa: E402

SRC = Path(r"C:\Users\Administrator\Desktop\T26单抽视频\视屏素材01\3\IMG_7530三色灯切换.MOV")
OUT = ROOT / "cache" / "verify"
OUT.mkdir(parents=True, exist_ok=True)


def sheet(name, ss, dur, fps, cols, rows, scale):
    out = OUT / name
    vf = f"fps={fps},scale={scale}:-2,tile={cols}x{rows}:padding=4:margin=6:color=white"
    args = ["-y", "-ss", f"{ss:.3f}", "-i", str(SRC), "-t", f"{dur:.3f}",
            "-vf", vf, "-frames:v", "1", "-q:v", "3", str(out)]
    r = media._run(args, timeout=180)
    ok = r.returncode == 0 and out.exists()
    print(f"{name}: {'OK' if ok else 'FAIL'}  frames~{int(dur*fps)}  span {ss:.1f}-{ss+dur:.1f}s")
    if not ok:
        print(r.stderr.decode("utf-8", errors="replace")[-500:])
    return str(out) if ok else ""


if __name__ == "__main__":
    info = media.probe(str(SRC))
    dur_s = info.get("duration_ms", 0) / 1000.0
    print(f"source: {SRC.name}")
    print(f"duration={dur_s:.2f}s  size={info.get('width')}x{info.get('height')}  "
          f"fps={info.get('fps')}  decode_ok={info.get('decode_ok')}")
    if dur_s <= 0:
        sys.exit(1)

    # 全片概览：每秒 1 帧，4x4，覆盖前 16 秒
    sheet("7530_overview.jpg", 0, min(16, dur_s), 1, 4, 4, 360)

    # 候选区间放大：3.0-13.0 秒，每 0.4 秒 1 帧，5x5
    start, span = 3.0, 10.0
    if dur_s > start:
        sheet("7530_candidate.jpg", start, min(span, dur_s - start), 2.5, 5, 5, 320)

    # 手部动作放大：0-3.5 秒，每 0.25 秒 1 帧，7x2
    sheet("7530_hand.jpg", 0, 3.5, 4, 7, 2, 330)

    print("output dir:", OUT)
