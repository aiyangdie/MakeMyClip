# -*- coding: utf-8 -*-
"""把 e2e_timeline.json 的排片结果渲染成一条可看的竖版短视频.
纯沙盒运行，用 ffmpeg，不触碰 MakeMyClip 生产代码与导出链。
"""
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = Path("F:/AI_Clip_Lab")
VIDEO = ROOT / "material/IMG_8886.MOV"
PLAN = ROOT / "reports/e2e_timeline.json"
TMP = ROOT / "reports/render_tmp"
TMP.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "reports/本地模型排片成片.mp4"

# 3:4 竖版 540x720，适合淘宝主图视频
W, H, FPS = 540, 720, 25


def run(args):
    r = subprocess.run(args, capture_output=True, text=True, errors="ignore")
    if r.returncode != 0:
        print("  [ffmpeg错误]", r.stderr[-400:])
    return r.returncode == 0


def make_clip(p, idx):
    """取 source_ms 处一帧，定格 target_ms 时长，输出竖版带字幕片段。"""
    src_s = p["source_ms"] / 1000.0
    dur = p["target_ms"] / 1000.0
    title = p["storyboard"]
    cue = (p.get("cues") or [p.get("caption", "")])[0][:18]
    # 字幕文字：分镜名 + 卖点，逗号在 drawtext 里需转义
    text = f"{title}｜{cue}".replace(",", "，").replace(":", "：")
    out = TMP / f"clip_{idx}.mp4"
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"drawbox=x=0:y=ih-110:w=iw:h=110:color=black@0.55:t=fill,"
        f"drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':text='{text}':"
        f"fontcolor=white:fontsize=30:x=(w-text_w)/2:y=h-95:"
        f"box=0"
    )
    # 第一步：抽一帧并画字幕，存成图片
    frame = TMP / f"frame_{idx}.png"
    if not run([
        FF, "-y", "-ss", f"{src_s:.3f}", "-i", str(VIDEO),
        "-vf", vf, "-frames:v", "1", str(frame),
    ]):
        print(f"  片段{idx} 抽帧失败")
        return None
    # 第二步：图片循环成定格视频（可靠做法）
    ok = run([
        FF, "-y", "-loop", "1", "-i", str(frame),
        "-t", f"{dur:.3f}", "-r", str(FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        str(out),
    ])
    print(f"  片段{idx} {title}: {'OK' if ok else '失败'} ({dur}s)")
    return out if ok else None


def main():
    print("=== 渲染本地模型排片结果成片 ===")
    d = json.loads(PLAN.read_text(encoding="utf-8"))
    plan = d["timeline_plan"]
    clips = []
    for i, p in enumerate(plan):
        c = make_clip(p, i)
        if c:
            clips.append(c)
    if not clips:
        print("没有可渲染的片段，中止")
        return

    # 拼接 + 每段之间 0.4s 叠化
    listfile = TMP / "concat.txt"
    listfile.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    print(f"拼接 {len(clips)} 个片段...")
    ok = run([
        FF, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-r", str(FPS), str(OUT),
    ])
    if ok and OUT.exists():
        size = OUT.stat().st_size / 1024 / 1024
        print(f"\n成片已生成: {OUT} ({size:.1f} MB)")
    else:
        print("\n拼接失败")


if __name__ == "__main__":
    main()
