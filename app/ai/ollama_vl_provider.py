# -*- coding: utf-8 -*-
"""本地 Ollama 视觉模型 Provider（Phase B）。

- 只访问本机 base_url（默认 127.0.0.1:11434），不上传外网。
- 输出仍走 BaseVisionProvider 统一结构：cues + need_review。
- 服务未就绪 / 超时 / 解析失败 → 由上层 factory 降级启发式。
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from .. import media
from .vision_provider import (
    ALL_CUES, BaseVisionProvider, CUE_HAND, CUE_LIGHT_STATES, CUE_LIGHT_SWITCH,
    CUE_MOTION, CUE_RECIPROCATING, CUE_SUBJECT_CLOSE, CUE_SUBJECT_WHOLE, _cue,
)


CONTROLLED_TAGS = [
    "color_temperature", "drawer_open_close", "lamp_rotate", "handle_closeup",
    "product_whole", "motion", "hand", "static",
]


class OllamaVLProvider(BaseVisionProvider):
    name = "ollama_qwen_vl"

    def __init__(self, base_url="http://127.0.0.1:11434", model="qwen3-vl:4b-instruct-q4_K_M",
                 timeout_sec=120, sample_interval_ms=800, max_samples=12, **_kw):
        self.base_url = (base_url or "http://127.0.0.1:11434").rstrip("/")
        self.model = model
        self.timeout_sec = int(timeout_sec or 120)
        self.sample_interval_ms = int(sample_interval_ms or 800)
        self.max_samples = int(max_samples or 12)

    def ping(self) -> bool:
        try:
            req = urllib.request.Request(self.base_url + "/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _sample_jpegs(self, path, start_ms, end_ms) -> List[bytes]:
        proxy = media.preview_link(path)
        cap = cv2.VideoCapture(proxy)
        if not cap.isOpened():
            return []
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        sf = max(0, int(start_ms / 1000.0 * fps))
        ef = max(sf + 1, int(end_ms / 1000.0 * fps))
        step = max(1, int(fps * self.sample_interval_ms / 1000.0))
        if (ef - sf) // step > self.max_samples:
            step = max(step, (ef - sf) // self.max_samples)
        out = []
        idx = sf
        while idx < ef and len(out) < self.max_samples:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, fr = cap.read()
            if not ok:
                break
            small = cv2.resize(fr, (480, int(480 * fr.shape[0] / max(1, fr.shape[1]))))
            ok2, buf = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            if ok2:
                out.append(buf.tobytes())
            idx += step
        cap.release()
        return out

    def _ask(self, jpeg: bytes) -> Dict[str, Any]:
        img_b64 = base64.b64encode(jpeg).decode("ascii")
        prompt = (
            "这是商品主图视频中的一帧。只根据画面如实判断。\n"
            "从下列标签中选最贴切的 1～3 个（可多选）："
            + ",".join(CONTROLLED_TAGS)
            + "。\n"
            "只输出 JSON："
            '{"tags":["标签"],"caption":"20字内客观描述","confidence":0到1小数,'
            '"need_review":true或false}\n'
            "不要编造材质、尺寸、承重等画面看不到的参数。"
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {"num_predict": 180, "temperature": 0.1},
        }
        # 绕过系统代理，避免本机 127.0.0.1 被劫持
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(
            self.base_url + "/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(req, timeout=self.timeout_sec) as resp:
            data = json.load(resp)
        raw = (data.get("response") or "").strip()
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return {"tags": [], "caption": raw[:80], "confidence": 0.3, "need_review": True}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {"tags": [], "caption": raw[:80], "confidence": 0.3, "need_review": True}

    @staticmethod
    def _tags_to_cues(tags: List[str], caption: str, conf: float, need_review: bool):
        labels = []
        tags = [t for t in (tags or []) if isinstance(t, str)]
        conf = max(0.2, min(0.75, float(conf or 0.4)))
        mapping = {
            "color_temperature": (CUE_LIGHT_SWITCH, "疑似灯光/色温切换"),
            "drawer_open_close": (CUE_RECIPROCATING, "疑似抽屉开合类往复动作"),
            "lamp_rotate": (CUE_RECIPROCATING, "疑似灯头旋转类动作"),
            "handle_closeup": (CUE_SUBJECT_CLOSE, "疑似拉手/细节近景"),
            "product_whole": (CUE_SUBJECT_WHOLE, "疑似产品整体视角"),
            "motion": (CUE_MOTION, "观察到画面运动"),
            "hand": (CUE_HAND, "疑似手部/前景遮挡"),
            "static": (CUE_MOTION, "画面基本静止"),
        }
        for t in tags:
            if t in mapping:
                code, name = mapping[t]
                labels.append(_cue(code, name, conf, f"VLM标签={t}；{caption}", need_review=True))
        if any(t == "color_temperature" for t in tags):
            labels.append(_cue(CUE_LIGHT_STATES, "观察到灯光状态变化线索", conf,
                               caption or "VLM 提示色温/灯光变化", need_review=True))
        if not labels:
            labels.append(_cue(CUE_SUBJECT_WHOLE, "VLM 未给出强标签", 0.35,
                               caption or "需人工核验", need_review=True))
        return labels

    def analyze_segment(self, path, start_ms, end_ms, progress_cb=None):
        result = {
            "ok": False, "error": "", "provider": self.name,
            "labels": [], "metrics": {}, "suggested_tags": [],
            "need_review": True, "review_reasons": [],
        }
        if not self.ping():
            result["error"] = "本地视觉模型服务未就绪（Ollama 未启动或无法连接）"
            return result
        frames = self._sample_jpegs(path, start_ms, end_ms)
        if not frames:
            result["error"] = "抽帧失败，无法调用视觉模型"
            return result
        votes: Dict[str, int] = {}
        captions = []
        confs = []
        for i, jpeg in enumerate(frames):
            if progress_cb:
                progress_cb(i, len(frames))
            try:
                ans = self._ask(jpeg)
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
                result["error"] = f"VLM 调用失败：{type(e).__name__}: {e}"
                return result
            for t in ans.get("tags") or []:
                if t in CONTROLLED_TAGS:
                    votes[t] = votes.get(t, 0) + 1
            if ans.get("caption"):
                captions.append(str(ans["caption"])[:40])
            try:
                confs.append(float(ans.get("confidence", 0.4)))
            except (TypeError, ValueError):
                confs.append(0.4)
        top = sorted(votes.items(), key=lambda x: -x[1])[:3]
        tags = [t for t, _ in top]
        caption = captions[0] if captions else ""
        conf = float(np.mean(confs)) if confs else 0.4
        result["labels"] = self._tags_to_cues(tags, caption, conf, True)
        result["suggested_tags"] = tags
        result["metrics"] = {
            "vlm_votes": votes,
            "vlm_caption": caption,
            "sample_frames": len(frames),
            "model": self.model,
        }
        result["review_reasons"] = ["本地视觉模型结论需人工核验，不作为质检证明"]
        result["need_review"] = True
        result["ok"] = True
        return result
