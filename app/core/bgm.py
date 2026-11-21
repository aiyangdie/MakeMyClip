# -*- coding: utf-8 -*-
"""本地合成的背景音乐（阶段十·参考片风格）。

参考真实淘宝主图视频：全程平稳、有轻快律动、不抢画面的背景音乐，
没有逐句念稿旁白。这里用 numpy 直接合成一段「柔和琶音 + 低音 + 轻节拍」，
完全离线、无版权、不上传、不依赖任何外部音频文件（可一键回退到用户自有音乐）。

原 audio_mixer 的正弦音垫 / 用户导入音乐逻辑一律保留不动。
"""
import math
import struct
import wave
from pathlib import Path

import numpy as np

SR = 44100

# 柔和的大调进行（C - Am - F - G），每个和弦 2 秒，循环铺满整段
# 频率：C4=261.63 E4=329.63 G4=392.00 A4=440.00 等
_CHORDS = [
    ("C", [261.63, 329.63, 392.00], 130.81),   # C 大三和弦
    ("Am", [220.00, 261.63, 329.63], 110.00),  # A 小三和弦
    ("F", [174.61, 220.00, 261.63], 87.31),    # F 大三和弦
    ("G", [196.00, 246.94, 293.66], 98.00),    # G 大三和弦
]


def _tone(freq, n, amp=0.2, decay=3.0, overtone=0.35):
    """一个带轻微二次谐波和指数衰减的柔和音（避免刺耳方波）。"""
    t = np.arange(n, dtype=np.float64) / SR
    env = np.exp(-decay * t)
    # 起音软化，去掉爆音
    attack = np.clip(t / 0.012, 0, 1)
    sig = (np.sin(2 * np.pi * freq * t)
           + overtone * np.sin(2 * np.pi * freq * 2 * t)
           + 0.12 * np.sin(2 * np.pi * freq * 3 * t))
    return amp * env * attack * sig


def _soft_kick(n):
    """柔和低频节拍点（正弦下滑 + 快速衰减），只提供律动不吵。"""
    t = np.arange(n, dtype=np.float64) / SR
    f = 90 * np.exp(-18 * t) + 48
    phase = 2 * np.pi * np.cumsum(f) / SR
    return 0.16 * np.sin(phase) * np.exp(-22 * t)


def _soft_hat(n, rng):
    """极轻的高频沙锤（带通噪声感），落在反拍。"""
    t = np.arange(n, dtype=np.float64) / SR
    noise = rng.standard_normal(n)
    # 一阶高通近似：相邻差分，突出高频
    hp = np.diff(np.concatenate([[0.0], noise]))
    return 0.020 * hp * np.exp(-70 * t)


def synth_bgm(duration_s, out_path, seed=7, volume=0.5):
    """合成一段平稳、有律动的无版权 BGM，输出 16-bit PCM wav。

    duration_s: 目标时长（秒）；seed: 固定随机种子保证可复现；
    volume: 整体音量 (0~1)。返回 {'ok','path','error','duration_s'}。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        total = max(1, int(round(float(duration_s) * SR)))
        track = np.zeros(total, dtype=np.float64)
        rng = np.random.default_rng(seed)

        beat = 0.5          # 每拍 0.5 秒（120 BPM）
        step = beat / 2     # 八分音符 0.25 秒，琶音步长
        chord_len = 2.0     # 每个和弦 2 秒

        def add(pos_s, sig):
            i = int(pos_s * SR)
            j = min(total, i + len(sig))
            if i < total and j > i:
                track[i:j] += sig[:j - i]

        # 1) 分解和弦琶音：每 0.25 秒一个音，三音循环 + 偶尔高八度，营造轻快律动
        pos = 0.0
        k = 0
        while pos < duration_s:
            chord = _CHORDS[int(pos // chord_len) % len(_CHORDS)]
            notes = chord[1]
            f = notes[k % len(notes)]
            if (k % 8) == 6:
                f *= 2.0  # 每小节一处高八度点缀
            n = int(0.42 * SR)
            add(pos, _tone(f, n, amp=0.16, decay=5.5, overtone=0.28))
            pos += step
            k += 1

        # 2) 低音根音：每拍一下，撑住和声
        pos = 0.0
        while pos < duration_s:
            chord = _CHORDS[int(pos // chord_len) % len(_CHORDS)]
            add(pos, _tone(chord[2], int(0.5 * SR), amp=0.20, decay=3.2, overtone=0.05))
            pos += beat

        # 3) 铺底 pad：每个和弦一个长音三和弦，音量很轻，保证能量平稳不断
        pos = 0.0
        while pos < duration_s:
            chord = _CHORDS[int(pos // chord_len) % len(_CHORDS)]
            n = int(chord_len * SR)
            t = np.arange(min(n, total - int(pos * SR)), dtype=np.float64) / SR
            pad = np.zeros_like(t)
            for f in chord[1]:
                pad += np.sin(2 * np.pi * f * t) + 0.2 * np.sin(2 * np.pi * 2 * f * t)
            # 缓慢的呼吸包络
            pad *= 0.030 * (0.75 + 0.25 * np.sin(2 * np.pi * 0.18 * t + pos))
            add(pos, pad)
            pos += chord_len

        # 4) 柔和节拍：每拍一个 kick，每个反拍一个极轻 hihat
        pos = 0.0
        while pos < duration_s:
            add(pos, _soft_kick(int(0.20 * SR)))
            add(pos + beat / 2, _soft_hat(int(0.08 * SR), rng))
            pos += beat

        # 5) 首尾淡入淡出 + 归一化 + 限幅
        fade = min(1.2, duration_s / 6.0)
        fi = int(fade * SR)
        if fi > 0:
            track[:fi] *= np.linspace(0, 1, fi)
            track[-fi:] *= np.linspace(1, 0, fi)
        peak = float(np.max(np.abs(track))) or 1.0
        track = track / peak * 0.85 * float(volume)
        track = np.clip(track, -1.0, 1.0)

        # 6) 写 16-bit 立体声 wav（左右轻微差异增强空间感，不刺耳）
        left = (track * 32767).astype(np.int16)
        right = (np.roll(track, 220) * 0.96 * 32767).astype(np.int16)
        pcm = np.empty(total * 2, dtype=np.int16)
        pcm[0::2] = left
        pcm[1::2] = right
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        return {"ok": True, "path": str(out_path), "error": "",
                "duration_s": round(duration_s, 2), "copyright": "local_synth"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "path": str(out_path), "error": f"{type(e).__name__}: {e}"}
