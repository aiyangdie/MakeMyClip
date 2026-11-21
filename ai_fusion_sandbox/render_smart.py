# -*- coding: utf-8 -*-
"""沙盒：用全片识别结果驱动选片，出一条真正由模型决定的动态成片。

与旧脚本的区别：
- 不再写死 SHOTS 时间点，全部读 full_shot_analysis.json 的 segments
- 覆盖整段视频，按内容去重选段，不让同一个卖点重复三遍
- 每段取原视频真实动态画面，绝不定格
- 解说词按每段画面单独生成，音画内容对齐
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import imageio_ffmpeg

sys.path.insert(0, "C:/Users/Administrator/WorkBuddy/2026-11-19-14-00-14/MakeMyClip")
from app.ai.tts_provider import provider_factory  # noqa: E402
from app.core import audio_mixer  # noqa: E402

FF = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = Path("F:/AI_Clip_Lab")
VIDEO = ROOT / "material/IMG_8886.MOV"
ANALYSIS = ROOT / "reports/full_shot_analysis.json"
TMP = ROOT / "reports/smart_tmp"
TMP.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "reports/本地模型内容选片成片_最终版.mp4"
NARRATIONS = ROOT / "reports/smart_narrations.json"
BGM = Path("C:/Users/Administrator/WorkBuddy/2026-11-19-14-00-14/MakeMyClip/cache/final/wizard_bgm.wav")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MODEL = "qwen3-vl:4b-instruct-q4_K_M"
W, H, FPS = 540, 720, 25
MAX_SEG = 6
SEG_DUR = 3.0


def log(msg):
    print(msg, flush=True)


def run(args, quiet=False):
    r = subprocess.run(args, capture_output=True, text=True, errors="ignore")
    if r.returncode != 0 and not quiet:
        log("  [ffmpeg错误] " + r.stderr[-300:])
    return r.returncode == 0


def rebuild_segments(frames, dur):
    """从逐帧原始判断重新分段：保留短特写，不吞并孤立卖点。"""
    rows = [(f["t"], f.get("shot", "未匹配")) for f in frames if "t" in f]
    rows.sort()
    if not rows:
        return []
    bounds, start = [], rows[0][0]
    for i in range(1, len(rows)):
        if rows[i][1] != rows[i - 1][1]:
            bounds.append((start, rows[i][0], rows[i - 1][1]))
            start = rows[i][0]
    bounds.append((start, dur, rows[-1][1]))
    out = []
    for a, b, lab in bounds:
        if b - a < 1.0:
            continue
        inside = [f for f in frames if a <= f.get("t", -1) < b]
        best = max(inside, key=lambda f: f.get("quality", 0)) if inside else {}
        out.append({
            "start": round(a, 2), "end": round(b, 2), "dur": round(b - a, 2),
            "shot": lab, "caption": best.get("caption", ""),
            "action": best.get("action", ""), "quality": best.get("quality", 0.5),
        })
    return out


def pick_segments(segs, max_n=8):
    """按时间叙事顺序选段：开场整体 + 各卖点一次 + 结尾整体必选。"""
    overall = [i for i, s in enumerate(segs) if s["shot"] == "产品整体亮相"]
    first, last = (overall[0], overall[-1]) if overall else (-1, -1)
    picked, used = [], set()
    for i, s in enumerate(segs):
        if i == last or s.get("dur", 0) < 1.2:
            continue
        lab = s["shot"]
        if lab == "产品整体亮相":
            if i != first or lab in used:
                continue
        else:
            if lab in used:
                continue
            used.add(lab)
        picked.append(s)
        if len(picked) >= max_n - 1:
            break
    if last >= 0 and last < len(segs):
        tail = segs[last]
        if tail.get("dur", 0) >= 1.2 and tail not in picked:
            picked.append(tail)
    return picked


def write_narration(seg):
    prompt = (
        "你是淘宝主图视频的导购文案。根据这个镜头画面，写一句12到20字的中文解说词，"
        "口语化、自然、适合念出来，只讲画面里真实看到的内容，不要编造，不要用引号。\n"
        f"分镜：{seg['shot']}\n画面：{seg.get('caption','')}\n动作：{seg.get('action','')}\n"
        "只输出这一句解说词。"
    )
    payload = {
        "model": MODEL, "prompt": prompt, "stream": False,
        "options": {"num_predict": 80, "temperature": 0.3},
    }
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with OPENER.open(req, timeout=150) as r:
            d = json.load(r)
        ans = d.get("response", "").strip().strip('"').strip("'")
        ans = re.sub(r"\s+", "", ans)[:30]
        return ans or seg.get("caption", ""), round(time.time() - t0, 1)
    except Exception as e:
        return seg.get("caption", ""), 0


def make_clip(i, seg, title, narration):
    """取模型指定时间段的真实动态画面 + 字幕。"""
    start = seg["start"]
    dur = min(seg["dur"], SEG_DUR)
    parts = [p for p in re.split(r"[，。！？]", narration) if p.strip()]
    cue = ""
    for part in parts:
        if len(cue) + len(part) > 12:
            break
        cue = (cue + "，" if cue else "") + part.strip()
    if not cue:
        cue = narration[:12]
    text = f"{title}｜{cue}".replace(",", "，").replace(":", "：").replace("'", "")
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
    log(f"  片段{i} [{start:.1f}-{start+dur:.1f}s] {title}: {'OK' if ok else '失败'}")
    return (out, dur) if ok else (None, dur)


def main():
    log("=== 模型内容选片 -> 动态成片（配音+BGM）===")
    d = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    all_segs = rebuild_segments(d["frames"], d["duration_s"])
    log(f"重新分段得到 {len(all_segs)} 个内容段（保留短特写）：")
    for s in all_segs:
        log(f"  {s['start']:5.1f}-{s['end']:5.1f}s ({s['dur']:4.1f}s) {s['shot']:8s} | {s['caption'][:24]}")
    segs = pick_segments(all_segs)
    log(f"\n按叙事顺序选中 {len(segs)} 段：")
    for s in segs:
        log(f"  {s['start']:5.1f}-{s['start']+min(s['dur'],SEG_DUR):5.1f}s {s['shot']:8s} | {s['caption'][:24]} | {s['action'][:14]}")

    log("\n按每段画面写解说词...")
    nars = []
    for i, s in enumerate(segs):
        txt, sec = write_narration(s)
        nars.append({"idx": i, "shot": s["shot"], "start": s["start"], "narration": txt})
        log(f"  片段{i} [{sec}s] {txt}")
    NARRATIONS.write_text(json.dumps(nars, ensure_ascii=False, indent=2), encoding="utf-8")

    log("\n剪真实动态片段...")
    clips, durs = [], []
    for i, s in enumerate(segs):
        c, dur = make_clip(i, s, s["shot"], nars[i]["narration"])
        if c:
            clips.append(c)
            durs.append(dur)

    listfile = TMP / "concat.txt"
    listfile.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    silent = TMP / "silent.mp4"
    log(f"拼接 {len(clips)} 段...")
    run([
        FF, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-r", str(FPS), str(silent),
    ])

    log("生成中文配音...")
    tts = provider_factory()
    voice_files, cursor = [], 0.0
    for i, nar in enumerate(nars[:len(clips)]):
        vp = TMP / f"voice_{i}.wav"
        r = tts.synthesize(nar["narration"], str(vp), rate=175)
        if r.get("ok"):
            info = subprocess.run([FF, "-i", str(vp)], capture_output=True, text=True, errors="ignore").stderr
            m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", info)
            vdur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 2.5
            if vdur > durs[i] + 0.3:
                tts.synthesize(nar["narration"], str(vp), rate=205)
            voice_files.append((vp, cursor))
            cursor += durs[i]
            log(f"  配音{i}: {nar['narration'][:22]}")

    narration_track = TMP / "narration_full.wav"
    if voice_files:
        inputs, filters, labels = [], [], []
        for j, (vp, offset) in enumerate(voice_files):
            inputs += ["-i", str(vp)]
            filters.append(f"[{j}:a]adelay={int(offset*1000)}|{int(offset*1000)}[v{j}]")
            labels.append(f"[v{j}]")
        filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest,alimiter=limit=0.95[aout]")
        run([FF, "-y", *inputs, "-filter_complex", ";".join(filters),
             "-map", "[aout]", "-t", f"{cursor:.1f}", str(narration_track)])

    total_ms = int(sum(durs) * 1000)
    log(f"混音（配音+BGM压低），视频 {total_ms/1000:.1f}s...")
    mix = audio_mixer.mix_audio(
        silent, narration_track if narration_track.exists() else None, BGM, OUT,
        enable_narration=True, enable_music=True,
        music_volume=0.18, duck=True, duration_ms=total_ms,
    )
    log("混音结果: " + str(mix))

    if mix.get("ok"):
        boosted = TMP / "boosted.mp4"
        if run([FF, "-y", "-i", str(OUT), "-af", "volume=3.0,alimiter=limit=0.95",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(boosted)]):
            import shutil
            shutil.move(str(boosted), str(OUT))

    if OUT.exists():
        import os
        log(f"\n成片: {OUT} ({os.path.getsize(OUT)/1024/1024:.1f} MB)")
        info = subprocess.run([FF, "-i", str(OUT)], capture_output=True, text=True, errors="ignore").stderr
        for line in info.splitlines():
            if "Duration" in line or "Stream #" in line:
                log("  " + line.strip()[:100])


if __name__ == "__main__":
    main()
