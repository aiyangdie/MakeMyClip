# -*- coding: utf-8 -*-
"""阶段五端到端测试：文案→配音→字幕→音乐→最终合成→三轨开关→保存重开。
全部使用真实素材与真实合成，不用 mock。"""
import sys, os, json, subprocess, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
from app import config, db as dbmod, media
from app.core import narration, subtitle, audio_mixer, final_exporter, video_editor
from app.ai import tts_provider

results = []
def check(name, cond, detail=""):
    results.append({"name": name, "pass": bool(cond), "detail": str(detail)})
    print(("PASS" if cond else "FAIL"), "|", name, "|", detail)

# 用独立测试库
dbp = config.DB_DIR / "_stage5_e2e.db"
if dbp.exists():
    dbp.unlink()
db = dbmod.ProjectDB(str(dbp))
db.set_project_name("阶段五测试")
db.init_storyboards(config.DEFAULT_STORYBOARD_TEMPLATE)

# ===== 真实时间线（复用阶段四的镜头结构，4 个真实素材镜头）=====
base = Path.home()/"Desktop"/"T26单抽视频"/"视屏素材01"
assets = [
    ("1/IMG_7520整体+细节.MOV", "产品整体亮相", 0, 3000),
    ("1/IMG_7523侧面转正整体.MOV", "台面材质和边缘", 0, 3000),
    ("3/IMG_7524开关抽屉.MOV", "抽屉开合", 0, 3000),
    ("4/IMG_7540旋转灯头7-11.MOV", "灯头旋转", 0, 3000),
]
from app import media as _media
for i, (rel, name, s, e) in enumerate(assets, 1):
    f = base / rel
    if not f.exists():
        print("素材缺失，跳过:", f); continue
    info = _media.probe(str(f))
    info["thumb_path"] = ""
    aid = db.add_asset(info)
    # 候选片段
    cid = db.add_clip({"storyboard_id": i, "asset_id": aid, "start_ms": s, "end_ms": e,
                       "primary_tag": name, "confidence": 0.7, "source": "test"})
    # 分镜绑定选片
    with db.connect() as c:
        c.execute("UPDATE storyboards SET selected_clip_id=?, status='已确认' WHERE id=?", (cid, i))
db.rebuild_timeline_from_storyboards()
shots = db.get_timeline()
check("建立真实镜头时间线", len(shots) >= 4, f"{len(shots)} 个镜头")

# ===== 1. 文案生成：不编造 =====
# 场景A：完全不填资料
r1 = narration.build_all(shots, {})
check("空资料时提示补全", "商品名称" in r1["missing"], r1["missing"])
check("空资料时文案无编造参数",
      all(x not in " ".join(l["text"] for l in r1["lines"])
          for x in ["尺寸", "承重", "瓦", "K色温", "认证"]),
      "文案只含中性描述")
check("空资料标题标注未填", "未填写" in r1["title"], r1["title"])
# 场景B：填真实资料
info = {"name": "带灯床头柜", "color": "白色", "material": "",
        "scene": "卧室", "selling": "", "load_bearing": "50kg"}
db.set_product_info(info)
r2 = narration.build_all(shots, db.get_product_info())
check("填商品名后进文案", any("带灯床头柜" in l["text"] for l in r2["lines"]),
      "整体/收尾镜头引用真实名称")
check("高风险参数进提醒而非文案",
      any("承重" in w for w in r2["warnings"]) and
      all("50kg" not in l["text"] for l in r2["lines"]),
      f"warnings={r2['warnings']}")
db.save_narration_lines(r2["lines"])
check("文案入库", len(db.get_narration_lines()) == len(r2["lines"]),
      f"{len(db.get_narration_lines())} 句")
# 核心：字幕只覆盖有素材的镜头，时间按成片顺序累计（不堆在0秒）
bound = [s for s in shots if s.get("asset_path")]
check("缺素材镜头不产生字幕行", len(r2["lines"]) == len(bound),
      f"字幕{len(r2['lines'])}行 / 有素材镜头{len(bound)}个")
check("字幕时间按成片顺序累计",
      r2["lines"][0]["start_ms"] == 0 and
      all(r2["lines"][i]["start_ms"] == r2["lines"][i-1]["end_ms"]
          for i in range(1, len(r2["lines"]))),
      f"首行0ms，逐行接续：{[l['start_ms'] for l in r2['lines']]}")

# ===== 2. 逐句编辑 =====
ln0 = db.get_narration_lines()[0]
db.update_narration_line(ln0["line_id"], text="这是用户手动改过的文案。", start_ms=100, end_ms=2900)
edited = db.get_narration_line(ln0["line_id"])
check("单句编辑生效", edited["text"] == "这是用户手动改过的文案。" and edited["start_ms"] == 100,
      "文字与时间都改了")

# ===== 3. 真实中文配音（本地 SAPI）=====
provider = tts_provider.provider_factory()
check("TTS 为本地离线", not provider.is_online(), provider.name())
voices = provider.list_voices()
check("存在中文语音", any("Chinese" in v["name"] or "Huihui" in v["name"] for v in voices),
      [v["name"] for v in voices])
lines = db.get_narration_lines()
voices_built = []
for ln in lines:
    rr = tts_provider.synthesize_cached(ln["text"], rate=160, provider=provider)
    if rr["ok"]:
        db.update_narration_line(ln["line_id"], voice_path=rr["path"])
        voices_built.append(rr["path"])
check("所有句子都合成出配音", len(voices_built) == len(lines),
      f"{len(voices_built)}/{len(lines)} 句")
# 缓存命中
rr2 = tts_provider.synthesize_cached(lines[0]["text"], rate=160, provider=provider)
check("配音缓存命中", rr2.get("cached"), "相同文案不重复合成")
# 校验第一条配音可解码
vi = media.probe(voices_built[0])
check("配音文件可解码", bool(vi.get("decode_ok")) and vi.get("duration_ms", 0) > 500,
      f"{vi.get('duration_ms')}ms")

# ===== 4. 字幕生成与同步 =====
srt = config.CACHE_DIR / "final" / "stage5.srt"
srt_r = subtitle.build_srt(db.get_narration_lines(), str(srt))
check("SRT 生成", srt_r["ok"] and srt_r["count"] == len(lines), f"{srt_r['count']} 条")
content = Path(srt["path"] if isinstance(srt, dict) else srt_r["path"]).read_text(encoding="utf-8-sig")
check("SRT 含中文字幕文本", "床头柜" in content or "手动改过" in content, "中文正常写入")

# ===== 5. 生成无声成片（阶段四引擎）=====
ep = {"ratio": "9:16 竖屏", "res": "720p", "fps": 30, "crf": 23}
rend = video_editor.render_all(shots, ep, db=db)
check("无声成片渲染", len(rend["segments"]) >= 4,
      f"新生成{rend['rendered']} 缓存{rend['cached']}")
silent = config.EXPORT_DIR / "_stage5_silent.mp4"
concat = video_editor.concat_segments(rend["segments"], str(silent))
check("无声成片拼接", concat["ok"], concat.get("error", "")[:100])
sv = video_editor.probe_output(str(silent))
check("无声成片可解码", sv["ok"], f"{sv.get('width')}x{sv.get('height')} {sv.get('duration_ms')}ms")

# ===== 6. 造测试音乐（测试用正弦波，不作为交付音乐）=====
music = config.CACHE_DIR / "final" / "_test_music.wav"
ff = media.ffmpeg_exe()
subprocess.run([ff, "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=15",
                "-c:a", "pcm_s16le", str(music)],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
check("测试音乐生成", music.exists(), "")

# ===== 7. 旁白轨：按镜头时间摆轨 =====
voices_with_time = [(ln["voice_path"], ln["start_ms"]) for ln in db.get_narration_lines()
                    if ln.get("voice_path") and Path(ln["voice_path"]).exists()]
ntrack = config.CACHE_DIR / "final" / "stage5_narration.wav"
nar_r = audio_mixer.build_narration_track(voices_with_time, sv["duration_ms"], ntrack)
check("旁白轨合成且时长对齐视频", nar_r["ok"], nar_r.get("error", "")[:100])
ninfo = media.probe(str(ntrack))
check("旁白轨覆盖视频全长", abs((ninfo.get("duration_ms") or 0) - sv["duration_ms"]) < 300,
      f"旁白{ninfo.get('duration_ms')}ms vs 视频{sv['duration_ms']}ms")

# ===== 8. 最终合成：三轨全开 =====
out_full = config.EXPORT_DIR / "阶段五_三轨全开.mp4"
res = final_exporter.export_final(
    str(silent), db.get_narration_lines(), str(srt), str(out_full),
    subtitle_style={"font": "Microsoft YaHei", "size": 36, "color": "#FFFFFF", "outline": 2, "alignment": 2},
    enable_subtitle=True, enable_narration=True, enable_music=True,
    narration_path=str(ntrack), music_path=str(music), music_volume=0.2,
    duck=True, duration_ms=sv["duration_ms"])
check("三轨全开最终成片", res["ok"], res.get("error", "")[:150])
if res["ok"]:
    finfo = video_editor.probe_output(str(out_full))
    check("最终成片可解码且时长正确",
          finfo["ok"] and abs(finfo["duration_ms"] - sv["duration_ms"]) < 300,
          f"{finfo.get('width')}x{finfo.get('height')} {finfo.get('duration_ms')}ms 音轨={video_editor.probe_output(str(out_full)).get('ok')}")
    check("最终成片带音轨", bool(media.probe(str(out_full)).get("has_audio")), "音轨存在")

# ===== 9. 三轨独立开关 =====
variants = [
    ("关旁白", dict(enable_narration=False, enable_music=True, narration_path=None)),
    ("关音乐", dict(enable_narration=True, enable_music=False, music_path=None)),
    ("关字幕", dict(enable_subtitle=False, enable_narration=True, enable_music=True)),
    ("全关", dict(enable_subtitle=False, enable_narration=False, enable_music=False)),
]
for label, overrides in variants:
    base_opts = dict(
        subtitle_style={"font": "Microsoft YaHei", "size": 36, "color": "#FFFFFF", "outline": 2},
        enable_subtitle=True, enable_narration=True, enable_music=True,
        narration_path=str(ntrack), music_path=str(music),
        music_volume=0.2, duck=True, duration_ms=sv["duration_ms"])
    base_opts.update(overrides)
    op = config.EXPORT_DIR / f"阶段五_{label}.mp4"
    r = final_exporter.export_final(str(silent), db.get_narration_lines(), str(srt), str(op), **base_opts)
    ok = r["ok"] and abs(video_editor.probe_output(str(op))["duration_ms"] - sv["duration_ms"]) < 300
    check(f"{label}仍能导出且时长正确", ok, r.get("error", "")[:80])

# ===== 10. 项目保存重开 =====
db2 = dbmod.ProjectDB(str(dbp))
lines2 = db2.get_narration_lines()
info2 = db2.get_product_info()
check("重开后文案行恢复", len(lines2) == len(lines), f"{len(lines2)} 句")
check("重开后单句编辑保留", lines2[0]["text"] == "这是用户手动改过的文案。", "")
check("重开后商品资料保留", info2.get("name") == "带灯床头柜", info2)
check("重开后配音路径保留", bool(lines2[0].get("voice_path")) and Path(lines2[0]["voice_path"]).exists(), "")

# ===== 输出 =====
passed = sum(1 for r in results if r["pass"])
out = {"stage": 5, "passed": passed, "total": len(results), "results": results,
       "final_video": str(out_full), "silent_video": str(silent)}
Path("tests/test_result_stage5.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n结果：{passed}/{len(results)} 通过")
sys.exit(0 if passed == len(results) else 1)
