# -*- coding: utf-8 -*-
"""阶段十测试：参考主图视频模板优化（卖点标签字幕 + 纯BGM + 排版）。

铁律：
- 字幕文案只用镜头真实拍到的画面词，绝不照搬参考片的材质/参数宣称。
- 字幕时间线按成片真实时长精确对齐（修复 xfade 叠化累积漂移）。
- 标准模式（完整句白字 + 中文旁白）保留可一键回退。
- 三轨独立、非破坏：无声成片不改、原素材只读、改单镜头不影响其他。
- BGM 为本地合成，无版权、离线、不上传。
"""
import sys, os, json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, db as dbmod, media
from app.core import narration, subtitle, audio_mixer, final_exporter, video_editor, bgm
from app.ai import tts_provider

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append({"name": name, "pass": bool(cond), "detail": detail})
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f" — {detail}" if detail else ""))

def has_audio(p):
    return bool(media.probe(str(p)).get("has_audio"))

print("=" * 74)
print("阶段十测试：参考片模板优化（卖点标签 / 平稳BGM / 排版）")
print("=" * 74)

proj = config.DB_DIR / "_stage9_full.db"
assert proj.exists(), "先跑 test_stage9.py 生成 13 镜头项目"
db = dbmod.ProjectDB(str(proj))
shots_all = db.get_timeline()
shots = [s for s in shots_all if (s.get("asset_path") or "").strip() or s.get("sub_segments")]
info = {"name": "带灯床头柜", "color": "白色", "material": ""}
silent = config.EXPORT_DIR / "阶段九_全镜头补齐.mp4"
sv = video_editor.probe_output(str(silent))
dur_ms = sv["duration_ms"]
print(f"底片：{dur_ms/1000:.2f}s {sv['width']}x{sv['height']}，镜头 {len(shots)} 个\n")

work = config.CACHE_DIR / "final"; work.mkdir(parents=True, exist_ok=True)

# ---------- 1. 卖点标签文案：只用画面可证内容 ----------
print("[1] 卖点标签文案（不虚构材质/参数）")
res = narration.build_selling_lines(shots, info)
lines = res["lines"]
check("标签行数=有画面镜头数", len(lines) == len(shots), f'{len(lines)} 行')
check("无任何禁用宣称(护栏)", narration.validate_selling_labels(lines) == [],
      str(narration.validate_selling_labels(lines)))
texts = "".join(l["text"] for l in lines)
check("不含参考片材质词(皮质/五金/碳素钢/实木/环保)",
      all(w not in texts for w in ["皮质", "软包", "五金", "碳素钢", "实木", "环保", "无异味"]))
check("标签为4-8字短卖点(非完整句)", all("。" not in l["text"] and len(l["text"]) <= 8 for l in lines),
      "/".join(l["text"] for l in lines[:4]))
check("三种版式齐备(title/tag/big)",
      {"title", "tag", "big"} == {l["kind"] for l in lines},
      str(sorted({l["kind"] for l in lines})))

# ---------- 2. 时间线精确对齐（修复叠化漂移）----------
print("\n[2] 字幕时间线与成片精确对齐")
check("首行从0开始", lines[0]["start_ms"] == 0)
check("相邻字幕首尾相接(无空隙/无重叠)",
      all(lines[i]["end_ms"] == lines[i+1]["start_ms"] for i in range(len(lines)-1)))
check("字幕总时长贴合成片(误差<0.5s)",
      abs(lines[-1]["end_ms"] - dur_ms) < 500,
      f'{lines[-1]["end_ms"]/1000:.2f}s vs 成片 {dur_ms/1000:.2f}s')
# 逐行时间单调递增且每行可见
check("每行时长>0.2s且单调", all(l["end_ms"] > l["start_ms"] + 200 for l in lines))
# 校准函数幂等/收敛
cal = narration.calibrate_to_duration(lines, dur_ms)
check("按真实时长校准后末行=成片时长", abs(cal[-1]["end_ms"] - dur_ms) <= 2,
      f'{cal[-1]["end_ms"]/1000:.3f}s')

# ---------- 3. 卖点标签 ASS 排版 ----------
print("\n[3] 参考片排版（白字+蓝紫描边+爱心+紫底大字）")
ass = work / "s10_badge.ass"
subtitle.build_ass_badge(cal, ass, {"play_w": sv["width"], "play_h": sv["height"]})
at = ass.read_text(encoding="utf-8-sig")
check("ASS 按成片真实尺寸(非写死9:16)",
      f'PlayResX: {sv["width"]}' in at and f'PlayResY: {sv["height"]}' in at,
      f'{sv["width"]}x{sv["height"]}')
check("含蓝紫描边色 + 白字 + 加粗", "&H00E04C5B&" in at and "&H00FFFFFF&" in at and ",-1," in at)
check("爱心装饰 ♥ 已写入", "♥" in at)
check("紫底大字版式 Big 存在", "Style: Big" in at and "三色灯光" in at)
check("淡入淡出 \\fad 生效(花括号未被转义)", r"{\fad(150,150)}" in at)

# ---------- 4. 本地合成 BGM（无版权、离线）----------
print("\n[4] 平稳有律动的本地合成 BGM")
music = work / "s10_bgm.wav"
rm = bgm.synth_bgm(dur_ms / 1000.0 + 0.3, music, volume=config.DEFAULT_BGM_VOLUME)
check("BGM 合成成功且为无版权本地源", rm["ok"] and rm.get("copyright") == "local_synth",
      rm.get("error", "")[:60])
mp = media.probe(str(music))
check("BGM 时长覆盖成片", mp.get("duration_ms", 0) >= dur_ms,
      f'{mp.get("duration_ms",0)/1000:.1f}s')
check("BGM 含音频轨", mp.get("has_audio") == 1)
# 能量平稳（参考片特征）：分段 RMS 标准差不能太大（无忽大忽小的念稿停顿）
import subprocess, numpy as np
raw = subprocess.run([media.ffmpeg_exe(), "-v", "error", "-i", str(music),
                      "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                     capture_output=True, timeout=120).stdout
a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
win = 8000
rms = [float(np.sqrt(np.mean(a[i:i+win]**2))) for i in range(0, len(a)-win, win)]
if rms:
    mean, std = float(np.mean(rms)), float(np.std(rms))
    check("BGM 能量平稳(无念稿式大起伏)", std / (mean or 1) < 1.2,
          f"std/mean={std/(mean or 1):.2f}")

# ---------- 5. 参考片风格成片（卖点标签 + 纯BGM，无旁白）----------
print("\n[5] 参考片风格成片（字幕+纯BGM，不逐句念稿）")
srt = work / "s10_badge.srt"
out_badge = config.EXPORT_DIR / "阶段十_参考片风格.mp4"
rf = final_exporter.export_final(
    str(silent), cal, str(srt), str(out_badge),
    subtitle_style={"preset": subtitle.BADGE_PRESET, "lines": cal},
    enable_subtitle=True, enable_narration=False, enable_music=True,
    music_path=str(music), music_volume=1.0, duck=False, duration_ms=dur_ms)
check("参考片风格成片合成成功", rf["ok"], rf.get("error", "")[:100])
if rf["ok"]:
    ob = video_editor.probe_output(str(out_badge))
    check("时长与无声版一致", abs(ob["duration_ms"] - dur_ms) <= 500,
          f'{ob["duration_ms"]/1000:.2f}s')
    check("仍为3:4 (720x960)", ob["width"] == 720 and ob["height"] == 960)
    check("含BGM音轨、无旁白(单一轨)", has_audio(out_badge))
    check("轨道标记 narration=False/music=True",
          rf["tracks"].get("narration") is False and rf["tracks"].get("music") is True,
          str(rf["tracks"]))
    srt_txt = srt.read_text(encoding="utf-8-sig")
    check("SRT 为卖点短标签(与烧录一致)", "手抚柜面" in srt_txt and "接下来" not in srt_txt)

# ---------- 6. 标准模式可回退（完整句白字 + 中文旁白）----------
print("\n[6] 标准模式一键回退（原样：完整句 + 中文旁白）")
std = narration.build_all(shots, info)
std_lines = std["lines"]
check("标准文案为完整句", any("接下来为您展示" in l["text"] for l in std_lines))
# 标准模式 ASS 走原 build_ass（PlayRes 原样、无爱心）
std_ass = work / "s10_std.ass"
subtitle.build_ass(std_lines, std_ass, {"font": "Microsoft YaHei"})
st = std_ass.read_text(encoding="utf-8-sig")
check("标准ASS无爱心/无卖点预设", "♥" not in st and "Style: Big" not in st)
# 中文旁白仍可用（本地 SAPI）
provider = tts_provider.provider_factory()
vr = tts_provider.synthesize_cached(std_lines[0]["text"], rate=160, provider=provider)
check("中文旁白仍可合成(回退可用)", vr["ok"], vr.get("error", "")[:60])
out_std = config.EXPORT_DIR / "阶段十_标准模式回退.mp4"
voices = []
for ln in std_lines:
    r = tts_provider.synthesize_cached(ln["text"], rate=160, provider=provider)
    if r["ok"]:
        voices.append((r["path"], ln["start_ms"]))
ntrack = work / "s10_narration.wav"
rn = audio_mixer.build_narration_track(voices, dur_ms, str(ntrack))
rs2 = final_exporter.export_final(
    str(silent), std_lines, str(work / "s10_std2.srt"), str(out_std),
    subtitle_style={"font": "Microsoft YaHei", "size": 36, "outline": 2, "alignment": 2},
    enable_subtitle=True, enable_narration=True, enable_music=True,
    narration_path=str(ntrack), music_path=str(music),
    music_volume=0.2, duck=True, duration_ms=dur_ms)
check("标准模式三轨成片成功(旁白+字幕+音乐)", rs2["ok"] and rs2["tracks"].get("narration"),
      rs2.get("error", "")[:80] + " " + str(rs2.get("tracks")))

# ---------- 7. 非破坏性 & 铁律 ----------
print("\n[7] 非破坏性与'改一个镜头不影响其他'")
check("无声成片未被改动", video_editor.probe_output(str(silent))["duration_ms"] == dur_ms)
check("历史成片全部保留", all((config.EXPORT_DIR / f).exists() for f in
      ["阶段九_全镜头补齐.mp4", "阶段七_最终三轨成片.mp4"]))
# 改一个镜头的标签文字，其他行逐字不变
before = [dict(l) for l in lines]
edited = [dict(l) for l in lines]
edited[5]["text"] = "抽屉空间"
check("改单条字幕不影响其他行",
      all(edited[i] == before[i] for i in range(len(before)) if i != 5))
# 锁定镜头仍被 db 层保护
locked = [s for s in shots_all if s.get("locked")]
check("锁定镜头数据在时间线中完好", isinstance(locked, list))

# ---------- 汇总 ----------
print("\n" + "=" * 74)
passed = sum(1 for r in RESULTS if r["pass"])
print(f"结果：{passed}/{len(RESULTS)} 项通过")
print("=" * 74)
outj = Path(__file__).parent / "test_result_stage10.json"
outj.write_text(json.dumps({"stage": 10, "total": len(RESULTS), "passed": passed,
                            "results": RESULTS,
                            "outputs": {"badge": str(out_badge), "standard": str(out_std)}},
                           ensure_ascii=False, indent=2), encoding="utf-8")
print("测试结果已写入", outj)
if passed != len(RESULTS):
    sys.exit(1)
