# -*- coding: utf-8 -*-
"""阶段七音频测试：给 27.1s 淘宝节奏成片配中文旁白 + 字幕 + 音乐垫。

复用阶段五音频流水线（TTS 本地 SAPI / libass 字幕 / 两步法混音）。
铁律：
- 商品信息只用已核实字段（名称=带灯床头柜、颜色=白色），材质未填 -> 如实列入提醒，不编造。
- 音乐为程序本地合成的柔和音垫（正弦和弦），无版权问题；用户可在界面换成自己的音乐。
- 字幕时长已按每镜头建议时长对齐（阶段七 [7] 已验证）。
"""
import sys, os, json, subprocess
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, db as dbmod, media
from app.core import narration, subtitle, audio_mixer, final_exporter, video_editor
from app.ai import tts_provider

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append({"name": name, "pass": bool(cond), "detail": detail})
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f" — {detail}" if detail else ""))

def has_audio(path):
    return bool(media.probe(str(path)).get("has_audio"))

print("=" * 72)
print("阶段七音频测试：旁白 + 字幕 + 音乐垫（真实素材成片）")
print("=" * 72)

proj = config.DB_DIR / "_stage7_e2e.db"
assert proj.exists(), "先跑 test_stage7.py 生成时间线与无声成片"
db = dbmod.ProjectDB(str(proj))

# ---------- 1. 文案（只用已核实信息） ----------
print("\n[1] 文案：只用已核实商品信息")
info = {"name": "带灯床头柜", "color": "白色", "material": ""}
db.set_product_info(info)
shots = db.get_timeline()
bound = [s for s in shots if s.get("asset_path") or s.get("sub_segments")]
nres = narration.build_all(bound, info)
check("文案行数=有画面镜头数", len(nres["lines"]) == len(bound), f'{len(nres["lines"])} 行')
check("材质未填被如实提醒(不编造)", any("材质" in m for m in nres["missing"]), str(nres["missing"]))
check("文案不含未填写的具体参数",
      all("板材" not in l["text"] and "承重" not in l["text"] for l in nres["lines"]))
db.save_narration_lines(nres["lines"])
lines = db.get_narration_lines()
print("    文案示例:", lines[0]["text"], "/", lines[-1]["text"])

# ---------- 2. 中文配音（本地 SAPI，离线） ----------
print("\n[2] 中文配音：本机语音，离线合成")
provider = tts_provider.provider_factory()
voices = []
for ln in lines:
    r = tts_provider.synthesize_cached(ln["text"], rate=160, provider=provider)
    if r["ok"]:
        voices.append((r["path"], ln["start_ms"]))
check("每句配音合成成功", len(voices) == len(lines), f'{len(voices)}/{len(lines)} 句')

# ---------- 3. 旁白轨 + 字幕 ----------
print("\n[3] 旁白轨与字幕")
silent = config.EXPORT_DIR / "阶段七_淘宝节奏成片.mp4"
sv = video_editor.probe_output(str(silent))
dur_ms = sv["duration_ms"]
work = config.CACHE_DIR / "final"; work.mkdir(parents=True, exist_ok=True)
ntrack = work / "stage7_narration.wav"
rn = audio_mixer.build_narration_track(voices, dur_ms, str(ntrack))
check("旁白轨合成成功", rn["ok"], rn.get("error", "")[:80])
srt = work / "stage7_stage7.srt"
rs = subtitle.build_srt(lines, str(srt))
check("字幕生成成功", srt.exists() and srt.stat().st_size > 100)
srt_text = srt.read_text(encoding="utf-8-sig")
check("首句字幕覆盖开场 0-4s", "00:00:00,000 --> 00:00:04,000" in srt_text)

# ---------- 4. 音乐垫（程序合成，无版权风险） ----------
print("\n[4] 音乐垫：程序本地合成（温和 A 大调正弦和弦）")
music = work / "stage7_music.wav"
dur_s = dur_ms / 1000 + 0.5
# 柔和音垫：A3+C#4+E4 和弦，0.2Hz 缓慢呼吸包络，首尾 1s 淡入淡出
expr = ("0.10*sin(220*2*PI*t)+0.08*sin(277.18*2*PI*t)"
        "+0.06*sin(329.63*2*PI*t)+0.04*sin(440*2*PI*t)")
rm = media._run(["-y", "-f", "lavfi", "-i",
                 f"aevalsrc={expr}:s=44100:d={dur_s:.2f}",
                 "-af", f"volume=0.6,afade=t=in:st=0:d=1,afade=t=out:st={dur_s-2:.2f}:d=2,"
                        "alimiter=limit=0.7",
                 "-c:a", "pcm_s16le", str(music)], timeout=90)
check("音乐垫合成成功", rm.returncode == 0 and music.exists() and music.stat().st_size > 1000,
      f'{dur_s:.1f}s 无版权程序合成')

# ---------- 5. 最终合成（三轨） ----------
print("\n[5] 最终合成：旁白+字幕+音乐（音乐自动避让旁白）")
out = config.EXPORT_DIR / "阶段七_最终三轨成片.mp4"
rf = final_exporter.export_final(
    str(silent), lines, str(srt), str(out),
    subtitle_style={"font": "Microsoft YaHei", "size": 36, "color": "#FFFFFF",
                    "outline": 2, "alignment": 2},
    enable_subtitle=True, enable_narration=True, enable_music=True,
    narration_path=str(ntrack), music_path=str(music), music_volume=0.2,
    duck=True, duration_ms=dur_ms)
check("最终成片合成成功", rf["ok"], rf.get("error", "")[:100])
fo = video_editor.probe_output(str(out))
check("时长与无声版一致(27.1s)", abs(fo["duration_ms"] - dur_ms) <= 500,
      f'{fo["duration_ms"]/1000:.2f}s vs {dur_ms/1000:.2f}s')
check("视频流仍为3:4 (720x960)", fo["width"] == 720 and fo["height"] == 960,
      f'{fo["width"]}x{fo["height"]}')
check("含音频轨(旁白+音乐)", has_audio(out))
check("无声版未被改动(非破坏)", silent.exists()
      and video_editor.probe_output(str(silent))["duration_ms"] == dur_ms)

# ---------- 汇总 ----------
print("\n" + "=" * 72)
passed = sum(1 for r in RESULTS if r["pass"])
print(f"结果：{passed}/{len(RESULTS)} 项通过")
print("=" * 72)
outj = Path(__file__).parent / "test_result_stage7_audio.json"
outj.write_text(json.dumps({"stage": "7-audio", "total": len(RESULTS), "passed": passed,
                            "results": RESULTS, "outputs": {"final": str(out)}},
                           ensure_ascii=False, indent=2), encoding="utf-8")
print("测试结果已写入", outj)
if passed != len(RESULTS):
    sys.exit(1)
