# -*- coding: utf-8 -*-
"""让本地视觉模型为每个分镜写一句导购解说词。
基于已识别的画面内容，生成口语化、能配音的商品介绍。沙盒运行。
"""
import json
import re
import time
import urllib.request
from pathlib import Path

OUT = Path("F:/AI_Clip_Lab/reports")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MODEL = "qwen3-vl:4b-instruct-q4_K_M"

# 每个镜头的画面（上一轮本地模型识别的原文）
FRAMES = [
    ("产品整体亮相", "米色柜体配台面与台灯整体展示"),
    ("灯罩细节", "米白色花瓣形灯罩，黑色金属支架"),
    ("产品整体亮相", "米色床头柜带抽屉和灯杆"),
    ("拉手特写", "手握金色拉手，展示抽屉开启细节"),
    ("拉手特写", "金色圆形拉手特写，质感清晰"),
    ("拉手特写", "金色球形拉手特写，质感清晰"),
]


def ask(text):
    prompt = (
        "你是淘宝主图视频的导购文案writer。根据这个镜头画面，写一句12-22字的中文解说词，"
        "口语化、自然、适合念出来，突出画面里真实看到的卖点，不要编造，不要标点冗长。\n"
        f"镜头：{text}\n"
        "只输出这一句解说词，不要引号、不要解释。"
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
        with OPENER.open(req, timeout=120) as r:
            d = json.load(r)
        ans = d.get("response", "").strip().strip('"').strip("'")
        ans = re.sub(r"\s+", "", ans)[:35]
        return ans, round(time.time() - t0, 1)
    except Exception as e:
        return "", 0


def main():
    print("=== 本地模型写导购解说词 ===")
    results = []
    for i, (sb, cap) in enumerate(FRAMES):
        txt, sec = ask(cap)
        if not txt:
            txt = cap
        results.append({"idx": i, "storyboard": sb, "caption": cap, "narration": txt})
        print(f"  镜头{i} [{sb} / {sec}s] -> {txt}")
    (OUT / "narrations.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n已保存 narrations.json")


if __name__ == "__main__":
    main()
