import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
from app.core import audio_mixer as am, subtitle
from app import media
import subprocess

# 用阶段四的成片做基底
video = Path("exports/_stage4_test_final.mp4")
nar = Path("tests/_probe_tts.wav")
print("基底成片存在:", video.exists(), "| 配音存在:", nar.exists())

# 造一段测试音乐（正弦波，仅测试用，不交付）
music = Path("tests/_probe_music.wav")
ff = media.ffmpeg_exe()
subprocess.run([ff,"-y","-f","lavfi","-i","sine=frequency=440:duration=12","-c:a","pcm_s16le",str(music)],
               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

out = Path("tests/_mix_both.mp4")
r = am.mix_audio(str(video), str(nar), str(music), str(out), True, True, music_volume=0.2, duck=True)
print("旁白+音乐(含降音):", "OK" if r["ok"] else "FAIL", "| 轨:", r["tracks"], "|", r["error"][:150])
if r["ok"]:
    info = media.probe(str(out))
    print("  成片: 时长", info.get("duration_ms"), "音轨", info.get("has_audio"), "解码", info.get("decode_ok"))

# 单独关音乐
out2 = Path("tests/_mix_no_music.mp4")
r2 = am.mix_audio(str(video), str(nar), None, str(out2), True, False)
print("关音乐:", "OK" if r2["ok"] else "FAIL", "| 轨:", r2["tracks"])
# 单独关旁白
out3 = Path("tests/_mix_no_nar.mp4")
r3 = am.mix_audio(str(video), None, str(music), str(out3), False, True, music_volume=0.2)
print("关旁白:", "OK" if r3["ok"] else "FAIL", "| 轨:", r3["tracks"])
# 全关
out4 = Path("tests/_mix_none.mp4")
r4 = am.mix_audio(str(video), None, None, str(out4), False, False)
print("全关(静音):", "OK" if r4["ok"] else "FAIL", "| 轨:", r4["tracks"], "|", r4["error"][:120])
