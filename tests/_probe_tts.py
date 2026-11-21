import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
import pyttsx3
from app import media

out = Path("tests/_probe_tts.wav")
engine = pyttsx3.init()
# 选中文语音
zh = [v for v in engine.getProperty('voices') if 'Huihui' in v.name or 'Chinese' in v.name]
print("中文语音:", [v.name for v in zh])
if zh:
    engine.setProperty('voice', zh[0].id)
engine.setProperty('rate', 150)
engine.setProperty('volume', 1.0)
text = "这款带灯床头柜，台面采用皮质设计，抽屉可以平稳开合。"
engine.save_to_file(text, str(out))
engine.runAndWait()
print("wav存在:", out.exists(), "大小:", out.stat().st_size if out.exists() else 0)
if out.exists():
    info = media.probe(str(out))
    print("时长ms:", info.get("duration_ms"), "解码:", info.get("decode_ok"), "错误:", info.get("error",""))
