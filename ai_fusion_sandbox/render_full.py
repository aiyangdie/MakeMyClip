# -*- coding: utf-8 -*-
"""完整成片：动态画面 + 中文字幕 + 本地模型写的配音 + BGM 自动压低。
复用 MakeMyClip 的 tts_provider 和 audio_mixer（只读调用，不改生产代码）。
沙盒运行。
"""
import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

# 复用生产项目的配音与混音模块
sys.path.insert(0, "C:/Users/Administrator/WorkBuddy/2026-11-19-14-00-14/MakeMyClip")
from app.ai.tts_provider import provider_factory  # noqa: E402
from app.core import audio_mixer  # noqa: E402

FF = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = Path("F:/AI_Clip_Lab")
VIDEO = ROOT / "material/IMG_8886.MOV"
TMP = ROOT / "reports/full_tmp"
TMP.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "reports/本地模型智能成片_带配音音乐.mp4"
BGM = Path("C:/Users/Administrator/WorkBuddy/2026-11-19-14-00-14/MakeMyClip/cache/final/wizard_bgm.wav")
W, H, FPS = 540, 720, 25

# 取原视频的真实片段：起点秒 + 时长秒，配合解说词
SHOTS = [
    (0.5, 3.5), (3.5, 3.0), (6.5, 3.0),
    (9.5, 3.0), (12.5, 3.0), (15.5, 3.0),
]


def run(args, quiet=False):
    r = subprocess.run(args, capture_output=True, text=True, errors="ignore")
    if r.returncode != 0 and not quiet:
        print("  [ffmpeg错误]", r.stderr[-300:])
    return r.returncode == 0


def make_clip(i, shot, title, narration):
    """取真实动态片段 + 字幕，输出定长片段。"""
    start, dur = shot
    text = f"{title}｜{narration[:10]}".replace(",", "，")
    out = TMP / f"clip_{i}.mp4"
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"drawbox=x=0:y=ih-110:w=iw:h=110:color=black@0.55:t=fill,"
        f"drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':text='{text}':"
        f"fontcolor=white:fontsize=28:x=(w-text_w)/2:y=h-92"
    )
    ok = run([
        FF, "-y", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(VIDEO),
        "-vf", vf, "-r", str(FPS), "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", str(out),
    ])
    print(f"  片段{i} {title}: {'OK' if ok else '失败'} ({dur}s)")
    return out if ok else None


def main():
    print("=== 完整智能成片 ===")
    nars = json.loads((ROOT / "reports/narrations.json").read_text(encoding="utf-8"))

    # 1) 动态画面片段
    clips = []
    for i, shot in enumerate(SHOTS):
        c = make_clip(i, shot, nars[i]["storyboard"], nars[i]["narration"])
        if c:
            clips.append(c)

    # 2) 拼接无声片（直接 concat，无叠化——保证时长精确、音画对齐）
    listfile = TMP / "concat.txt"
    listfile.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    silent = TMP / "silent.mp4"
    print("拼接动态片段...")
    run([
        FF, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-r", str(FPS), str(silent),
    ])

    # 3) 每段配音 -> 按时间轴拼成一条完整旁白音轨
    print("生成中文配音...")
    tts = provider_factory()
    voice_files = []
    cursor = 0.0
    offsets = []
    for i, nar in enumerate(nars):
        vp = TMP / f"voice_{i}.wav"
        r = tts.synthesize(nar["narration"], str(vp), rate=175)
        if r.get("ok"):
            # 探测配音时长
            info = subprocess.run([FF, "-i", str(vp)], capture_output=True, text=True, errors="ignore").stderr
            import re
            m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", info)
            vdur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 2.5
            # 若配音比画面长，压缩语速重来一次
            if vdur > SHOTS[i][1] + 0.3:
                r = tts.synthesize(nar["narration"], str(vp), rate=210)
            voice_files.append((vp, cursor))
            offsets.append((cursor, round(cursor + min(vdur, SHOTS[i][1]), 2)))
            cursor += SHOTS[i][1]
            print(f"  配音{i}: {nar['narration'][:20]}...")
        else:
            print(f"  配音{i} 失败: {r.get('error')}")

    # 用 adelay 把每段配音放到对应时间点，再混成一条旁白轨
    narration_track = TMP / "narration_full.wav"
    if voice_files:
        inputs, filters, labels = [], [], []
        for j, (vp, offset_ms) in enumerate(voice_files):
            inputs += ["-i", str(vp)]
            filters.append(f"[{j}:a]adelay={int(offset_ms*1000)}|{int(offset_ms*1000)}[v{j}]")
            labels.append(f"[v{j}]")
        filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest,alimiter=limit=0.95[aout]")
        run([
            FF, "-y", *inputs, "-filter_complex", ";".join(filters),
            "-map", "[aout]", "-t", "19", str(narration_track),
        ])

    # 4) 混音：配音 + BGM（音乐自动压低）
    total_ms = len(SHOTS) * 3000
    print(f"混音（配音+BGM压低），视频时长 {total_ms/1000}s...")
    mix = audio_mixer.mix_audio(
        silent, narration_track if narration_track.exists() else None, BGM, OUT,
        enable_narration=True, enable_music=True,
        music_volume=0.18, duck=True, duration_ms=total_ms,
    )
    print("混音结果:", mix)

    # 5) 整体提亮音量：normalize 让配音清楚（沙盒后处理，不改生产代码）
    if mix.get("ok"):
        boosted = TMP / "boosted.mp4"
        ok = run([
            FF, "-y", "-i", str(OUT),
            "-af", "volume=3.0,alimiter=limit=0.95",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(boosted),
        ])
        if ok and boosted.exists():
            import shutil
            shutil.move(str(boosted), str(OUT))

    if OUT.exists():
        import os
        print(f"\n成片: {OUT} ({os.path.getsize(OUT)/1024/1024:.1f} MB)")
        # 打印音轨信息
        info = subprocess.run([FF, "-i", str(OUT)], capture_output=True, text=True, errors="ignore").stderr
        for line in info.splitlines():
            if "Duration" in line or "Stream #" in line:
                print("  " + line.strip()[:100])


if __name__ == "__main__":
    main()
