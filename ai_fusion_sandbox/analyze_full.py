# -*- coding: utf-8 -*-
"""沙盒：全片逐帧识别 -> 内容驱动的镜头分段（替代机械3秒均分）。

改进点：
1. 覆盖整段 29.7 秒，不再只取前 18 秒
2. 每 1.5 秒抽一帧让本地 VLM 判断"这一帧属于哪个卖点镜头"
3. 把连续相同卖点的帧合并成镜头段，得到真正由内容决定的切点
只写沙盒报告，不碰 MakeMyClip 生产代码。
"""
import base64
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = Path("F:/AI_Clip_Lab")
VIDEO = ROOT / "material/IMG_8886.MOV"
FRAMES = ROOT / "reports/full_frames"
FRAMES.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "reports/full_shot_analysis.json"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MODEL = "qwen3-vl:4b-instruct-q4_K_M"

STEP = 1.5  # 每 1.5 秒抽一帧
RECIPE = [
    "产品整体亮相", "台面材质和边缘", "拉手特写", "抽屉开合", "抽屉内部",
    "柜脚和底部", "灯杆调节", "灯头旋转", "三色温切换", "灯罩细节",
    "实体开关按钮", "整体收尾",
]


def log(msg):
    print(msg, flush=True)


def probe_duration(path):
    r = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True, errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 30.0


def extract_frame(t, out):
    subprocess.run(
        [FF, "-y", "-ss", f"{t:.2f}", "-i", str(VIDEO), "-frames:v", "1",
         "-vf", "scale=480:-1", "-q:v", "6", str(out)],
        capture_output=True, errors="ignore",
    )
    return out.exists()


def ask_vlm(img_path, t):
    img = base64.b64encode(Path(img_path).read_bytes()).decode()
    prompt = (
        "这是淘宝主图视频（一个带花瓣台灯的米色床头柜）在 %.1f 秒处的一帧画面。\n" % t +
        "请判断这一帧最适合放进下面哪个分镜，并描述你真实看到的画面。\n"
        "可选分镜：" + "、".join(RECIPE) + "。\n"
        "只输出JSON：{\"shot\":\"从可选分镜里选最匹配的一个\","
        "\"caption\":\"20字内客观描述画面\","
        "\"action\":\"画面里正在发生什么动作，纯静止就写静止\","
        "\"quality\":0到1的小数}\n"
        "要求：只描述画面里确实看到的，不要编造卖点。"
    )
    payload = {
        "model": MODEL, "prompt": prompt, "images": [img], "stream": False,
        "options": {"num_predict": 200, "temperature": 0.1},
    }
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with OPENER.open(req, timeout=200) as resp:
            d = json.load(resp)
        raw = d.get("response", "").strip()
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            data = json.loads(m.group(0))
        else:
            data = {"shot": "未匹配", "caption": raw[:60], "action": "未知", "quality": 0.4}
        data["sec"] = round(time.time() - t0, 1)
        return data
    except Exception as e:
        return {"shot": "识别失败", "caption": str(e)[:60], "action": "未知",
                "quality": 0.0, "sec": 0}


def smooth_segments(results, times, dur):
    """把逐帧判断合并成镜头段：连续>=2帧相同卖点才算一段，孤立帧归并到相邻。"""
    labels = [r.get("shot", "未匹配") for r in results]
    n = len(labels)
    # 孤立单点修正
    for i in range(1, n - 1):
        if labels[i] != labels[i - 1] and labels[i] != labels[i + 1]:
            labels[i] = labels[i - 1]
    bounds = [(0.0, STEP * 1.0, labels[0])]
    start = 0.0
    for i in range(1, n):
        if labels[i] != labels[i - 1]:
            bounds.append((start, times[i], labels[i - 1]))
            start = times[i]
    bounds.append((start, dur, labels[-1]))
    segs = []
    for a, b, lab in bounds:
        if b - a < 0.8:
            continue
        inside = [r for r, tm in zip(results, times) if a <= tm < b]
        cap = max(inside, key=lambda r: r.get("quality", 0)).get("caption", "") if inside else ""
        act = max(inside, key=lambda r: r.get("quality", 0)).get("action", "") if inside else ""
        q = max((r.get("quality", 0) for r in inside), default=0.5)
        segs.append({
            "start": round(a, 2), "end": round(b, 2), "dur": round(b - a, 2),
            "shot": lab, "caption": cap, "action": act, "quality": q,
            "frames": len(inside),
        })
    return segs


def main():
    log("=== 全片逐帧识别（内容驱动选片）===")
    dur = probe_duration(VIDEO)
    times = [round(i * STEP, 2) for i in range(int(dur / STEP) + 1)]
    log(f"视频 {dur:.1f}秒，抽帧 {len(times)} 张：{times[:5]}...{times[-3:]}")

    results = []
    for i, t in enumerate(times):
        fp = FRAMES / f"f_{i:03d}.jpg"
        if not extract_frame(t, fp):
            results.append({"shot": "抽帧失败", "caption": "", "action": "", "quality": 0, "sec": 0})
            continue
        r = ask_vlm(fp, t)
        r["t"] = t
        results.append(r)
        log(f"  [{t:5.1f}s/{r['sec']:4.1f}s] {r.get('shot','?'):8s} | {r.get('caption','')[:26]} | {r.get('action','')[:14]}")

    segs = smooth_segments(results, times, dur)
    log(f"\n合并得到 {len(segs)} 个内容镜头段：")
    for s in segs:
        log(f"  {s['start']:5.1f}-{s['end']:5.1f}s ({s['dur']:4.1f}s) {s['shot']:8s} | {s['caption'][:24]} | {s['action'][:12]}")

    out = {
        "video": str(VIDEO), "duration_s": round(dur, 2), "step_s": STEP,
        "model": MODEL, "frames": results, "segments": segs,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\n已保存 {OUT}")


if __name__ == "__main__":
    main()
