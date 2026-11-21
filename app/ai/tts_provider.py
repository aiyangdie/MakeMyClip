# -*- coding: utf-8 -*-
"""可替换的中文 TTS 接口（阶段五）。

重要事实（如实记录，不夸大）：
- 本机检测到微软中文语音（Microsoft Huihui Desktop - Chinese (Simplified)），
  经实测能把中文句子合成为可解码的 WAV 文件（见 tests/_probe_tts.py）。
- 该实现完全走 Windows 本地 SAPI5 引擎：不联网、不上传任何商品视频或文案、无 API 费用。
- 声音是系统自带的机械感女声，不是云端大模型那种自然音色——这是本地方案的真实局限。
- 接口做成可替换：以后若用户愿意接受联网+上传+费用，可另写一个 provider 接云端音色，
  程序其余部分不用改。默认绝不使用联网方案。

商品保护：TTS 只朗读用户确认过的文案，不生成、不改写商品事实。
"""
import hashlib
from abc import ABC, abstractmethod

from .. import config

AUDIO_CACHE_DIR = config.CACHE_DIR / "audio"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class BaseTTSProvider(ABC):
    """TTS 可替换接口。任何实现都要提供下面四个方法。"""

    @abstractmethod
    def name(self):
        """接口显示名，如『本地中文语音（Windows 离线）』。"""

    @abstractmethod
    def list_voices(self):
        """返回 [{'id':..., 'name':..., 'language':...}, ...]。"""

    @abstractmethod
    def synthesize(self, text, out_path, voice_id=None, rate=160, volume=1.0):
        """把文本合成为 wav。返回 {'ok', 'path', 'error'}。"""

    def is_online(self):
        """是否会联网/上传数据。默认本地实现返回 False。"""
        return False


class WindowsSAPIProvider(BaseTTSProvider):
    """Windows 本地 SAPI5 实现（pyttsx3）。离线、免费、不上传。"""

    def name(self):
        return "本地中文语音（Windows 离线·不上传）"

    def _engine(self):
        import pyttsx3
        eng = pyttsx3.init()
        return eng

    def list_voices(self):
        try:
            eng = self._engine()
            voices = []
            for v in eng.getProperty("voices"):
                voices.append({
                    "id": v.id,
                    "name": v.name,
                    "language": getattr(v, "languages", [""])[0] if getattr(v, "languages", None) else "",
                })
            return voices
        except Exception:  # noqa: BLE001
            return []

    def synthesize(self, text, out_path, voice_id=None, rate=160, volume=1.0):
        if not text or not text.strip():
            return {"ok": False, "error": "文案为空，跳过配音"}
        try:
            from pathlib import Path
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            eng = self._engine()
            # 未指定时优先挑中文语音
            if not voice_id:
                zh = [v for v in eng.getProperty("voices")
                      if "Chinese" in v.name or "Huihui" in v.name
                      or "Yaoyao" in v.name or "Kangkang" in v.name
                      or "zh" in str(getattr(v, "languages", "")).lower()]
                if zh:
                    voice_id = zh[0].id
            if voice_id:
                eng.setProperty("voice", voice_id)
            eng.setProperty("rate", int(rate))
            eng.setProperty("volume", float(volume))
            eng.save_to_file(text, str(out_path))
            eng.runAndWait()
            if not out_path.exists() or out_path.stat().st_size < 500:
                return {"ok": False, "error": "配音文件为空（系统语音可能不可用）"}
            return {"ok": True, "path": str(out_path), "error": ""}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def is_online(self):
        return False


def provider_factory(name=None):
    """按名字取 provider。目前只有本地实现；预留云端实现的接入点。"""
    key = (name or "local").lower()
    if key in ("local", "windows", "sapi", "本地"):
        return WindowsSAPIProvider()
    # 未来：elif key == "cloud": return CloudTTSProvider(...)
    # 未注册的名字一律回退本地，避免误接联网服务。
    return WindowsSAPIProvider()


def cache_key(text, voice_id="", rate=160, volume=1.0):
    """文案/语音/语速/音量任一变化才重新配音。"""
    raw = f"{text}|{voice_id}|{rate}|{volume}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def synthesize_cached(text, voice_id=None, rate=160, volume=1.0,
                      provider=None, force=False):
    """带缓存的配音：同样文案与参数直接复用 WAV，避免重复合成。"""
    provider = provider or provider_factory()
    key = cache_key(text, voice_id or "default", rate, volume)
    out = AUDIO_CACHE_DIR / f"tts_{key}.wav"
    if out.exists() and out.stat().st_size > 500 and not force:
        return {"ok": True, "path": str(out), "error": "", "cached": True}
    r = provider.synthesize(text, out, voice_id=voice_id, rate=rate, volume=volume)
    r["cached"] = False
    return r
