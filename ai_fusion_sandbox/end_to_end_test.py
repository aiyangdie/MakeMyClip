# -*- coding: utf-8 -*-
"""沙盒端到端验证：本地模型识别视频 -> 找剪辑点 -> 按 MakeMyClip 菜谱排片.
只在 F:/AI_Clip_Lab 沙盒运行，不触碰 MakeMyClip 生产代码与数据库。
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
VIDEO = "F:/AI_Clip_Lab/material/IMG_8886.MOV"
OUT = Path("F:/AI_Clip_Lab/reports")
FRAMES = OUT / "e2e_frames"
FRAMES.mkdir(parents=True, exist_ok=True)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MODEL = "qwen3-vl:4b-instruct-q4_K_M"

# MakeMyClip 的 12 个分镜菜谱（来自 templates/furniture/nightstand.json）
RECIPE = [
    "产品整体亮相", "台面材质和边缘", "拉手特写", "抽屉开合", "抽屉内部",
    "柜脚和底部", "灯杆调节", "灯头旋转", "三色温切换", "灯罩细节",
    "实体开关按钮", "整体收尾",
]
TARGET_MS = {
    "产品整体亮相": 4000, "台面材质和边缘": 2500, "拉手特写": 2000,
    "抽屉开合": 5000, "抽屉内部": 2500, "柜脚和底部": 2000,
    "灯杆调节": 3000, "灯头旋转": 4000, "三色温切换": 6000,
    "灯罩细节": 2500, "实体开关按钮": 2500, "整体收尾": 4000,
}


def log(msg):
    print(msg, flush=True)


def probe_duration(path):
    r = subprocess.run([FF, "-i", path], capture_output=True, text=True, errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        return 6.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def detect_cuts(path, dur):
    """先用 ffmpeg 场景检测找切点；不足 3 个则按固定间隔均分。"""
    r = subprocess.run(
        [FF, "-i", path, "-vf", "select='gt(scene,0.25)',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, errors="ignore",
    )
    pts = [float(x) for x in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
    cuts = sorted({round(p, 2) for p in pts if 0.3 < p < dur - 0.3})
    method = "场景检测"
    if len(cuts) < 2:
        step = max(1.5, min(3.0, dur / 5))
        cuts = [round(i * step, 2) for i in range(1, int(dur / step))]
        method = "固定间隔(场景切换不明显，按时间均分模拟剪辑点)"
    cuts = cuts[:6]
    return cuts, method


def extract_frame(path, t, out):
    subprocess.run(
        [FF, "-y", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1",
         "-vf", "scale=480:-1", "-q:v", "6", str(out)],
        capture_output=True, errors="ignore",
    )
    return out.exists()


def ask_vlm(img_path, shot_idx, t):
    img = base64.b64encode(Path(img_path).read_bytes()).decode()
    prompt = (
        "这是淘宝商品主图视频的一个镜头画面。请判断这个镜头适合放进下面哪个分镜，并描述你看到的卖点。\n"
        "可选分镜：" + "、".join(RECIPE) + "。\n"
        "只输出JSON，格式：{\"shot\":\"从可选分镜里选最匹配的一个\",\"caption\":\"这一镜头展示了什么，30字内\","
        "\"cues\":[\"你实际看到的卖点细节\"],\"quality\":0到1的小数,\"worth_keeping\":true或false}\n"
        "要求：只描述画面里确实看到的，不要编造；不确定的卖点不要写。"
    )
    payload = {
        "model": MODEL, "prompt": prompt, "images": [img],
        "stream": False, "options": {"num_predict": 220, "temperature": 0.1},
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
        sec = round(time.time() - t0, 1)
        # 提取 JSON
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            data = json.loads(m.group(0))
        else:
            data = {"shot": "未匹配", "caption": raw[:80], "cues": [], "quality": 0.5, "worth_keeping": True}
        data["sec"] = sec
        data["t"] = t
        data["idx"] = shot_idx
        return data
    except Exception as e:
        return {"shot": "识别失败", "caption": str(e)[:80], "cues": [],
                "quality": 0.0, "worth_keeping": False, "sec": 0, "t": t, "idx": shot_idx}


def main():
    log("=== 端到端测试：本地模型识别 -> 找剪辑点 -> 按菜谱排片 ===")
    dur = probe_duration(VIDEO)
    log(f"视频时长: {dur:.1f}秒")
    cuts, method = detect_cuts(VIDEO, dur)
    log(f"剪辑点({method}): {cuts}")

    bounds = [0.0] + cuts + [dur]
    shots = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] - bounds[i] > 0.4]
    shots = shots[:6]
    log(f"共 {len(shots)} 个镜头待识别")

    results = []
    for i, (a, b) in enumerate(shots):
        mid = (a + b) / 2
        fp = FRAMES / f"shot_{i}.jpg"
        if not extract_frame(VIDEO, mid, fp):
            log(f"  镜头{i} 抽帧失败")
            continue
        r = ask_vlm(fp, i, mid)
        results.append(r)
        log(f"  镜头{i} [{a:.1f}-{b:.1f}s / {r['sec']}s] -> {r.get('shot')} | {r.get('caption','')[:50]}")

    # 按菜谱排片：每个分镜选质量最高、值得保留的镜头
    plan = []
    used = set()
    for sb in RECIPE:
        cands = [r for r in results if r.get("shot") == sb and r.get("worth_keeping") and r["idx"] not in used]
        if not cands:
            continue
        best = max(cands, key=lambda x: x.get("quality", 0))
        used.add(best["idx"])
        plan.append({
            "storyboard": sb,
            "source_ms": round(best["t"] * 1000),
            "target_ms": TARGET_MS.get(sb, 2500),
            "caption": best.get("caption", ""),
            "cues": best.get("cues", []),
            "quality": best.get("quality", 0),
            "confidence": round(min(0.92, 0.5 + best.get("quality", 0) * 0.4), 2),
        })

    out = {
        "video": VIDEO, "duration_s": round(dur, 1), "cut_method": method,
        "cuts_s": cuts, "shot_recognition": results, "timeline_plan": plan,
        "total_target_ms": sum(p["target_ms"] for p in plan),
    }
    (OUT / "e2e_timeline.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\n排片结果: {len(plan)}/{len(RECIPE)} 个分镜有画面, 目标总时长 {out['total_target_ms']/1000:.1f}秒")
    for p in plan:
        log(f"  - {p['storyboard']}: {p['source_ms']}ms取画面, {p['target_ms']}ms时长, 置信{p['confidence']}")
    log("\n已保存 F:/AI_Clip_Lab/reports/e2e_timeline.json")


if __name__ == "__main__":
    main()
