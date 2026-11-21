# -*- coding: utf-8 -*-
"""字幕生成与烧录（阶段五）。

- 从逐句文案 + 镜头时间生成标准 SRT（可导出给用户）。
- 用 FFmpeg 的 subtitles 滤镜把 SRT 内嵌进 MP4（libass 已在环境验证可用）。
- 支持：字体/字号/颜色/描边/位置、逐句时间调整、字幕独立开关。
- 字幕默认放画面底部，避开拉手、灯头、实体开关等关键卖点（任务书要求）。
"""
import subprocess
from pathlib import Path

from .. import config, media


def ms_to_srt_time(ms):
    ms = int(max(0, ms))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(lines, out_path):
    """lines: [{'text','start_ms','end_ms'}, ...] -> 写 SRT 文件。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for i, ln in enumerate(lines, 1):
        text = (ln.get("text") or "").strip().replace("\n", " ")
        if not text:
            continue
        start = ms_to_srt_time(ln.get("start_ms", 0))
        end = ms_to_srt_time(ln.get("end_ms", 0))
        blocks.append(f"{i}\n{start} --> {end}\n{text}\n")
    out_path.write_text("\n".join(blocks), encoding="utf-8-sig")
    return {"ok": True, "path": str(out_path), "count": len(blocks)}


def _ass_color(hex_color):
    """#RRGGBB -> ASS 的 &HBBGGRR&（libass 用 BGR 顺序）。"""
    h = (hex_color or "#FFFFFF").lstrip("#")
    if len(h) != 6:
        return "&H00FFFFFF&"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}&".upper()


def _escape_ass(text):
    return (text or "").replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def build_ass(lines, out_path, style=None):
    """生成带样式的 ASS（字体/字号/颜色/描边/位置）。返回 {'ok','path'}。"""
    style = style or {}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    font = style.get("font", "Microsoft YaHei")
    size = int(style.get("size", 36))
    primary = _ass_color(style.get("color", "#FFFFFF"))
    outline = int(style.get("outline", 2))
    # Alignment: 2=底部居中（避开关键卖点），8=顶部居中
    align = int(style.get("alignment", 2))
    margin_v = int(style.get("margin_v", 40))

    # 【阶段十二】画布按成片真实比例自适应；缺省仍是 720x1280，旧调用行为不变。
    play_w = int(style.get("play_w", 720))
    play_h = int(style.get("play_h", 1280))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{font},{size},{primary},&H000000FF&,&H00000000&,&H80000000&,0,0,0,0,100,100,0,0,1,{outline},1,{align},30,30,{margin_v},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events = []
    for ln in lines:
        text = _escape_ass((ln.get("text") or "").strip())
        if not text:
            continue
        s = ms_to_ass_time(ln.get("start_ms", 0))
        e = ms_to_ass_time(ln.get("end_ms", 0))
        events.append(f"Dialogue: 0,{s},{e},Default,,0,0,0,,{text}")
    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
    return {"ok": True, "path": str(out_path)}


def ms_to_ass_time(ms):
    ms = int(max(0, ms))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, cs = divmod(ms, 1000)
    return f"{h:d}:{m:02d}:{s:02d}.{cs//10:02d}"


# ===========================================================================
# 【阶段十增补 · 参考片风格字幕排版】
# 参考真实淘宝主图视频总结的排版：白色加粗圆体 + 蓝紫描边、左右爱心、底部居中，
# 文案为 4-8 字卖点标签；另支持开场标题、切光大字（紫底白字）两种版式。
# 原有 build_ass / burn_subtitles 的默认行为完全不变（preset 缺省即原样）。
# ===========================================================================

BADGE_PRESET = "selling_badge"

# 蓝紫描边（参考片主色）；ASS 颜色为 &HAABBGGRR&
_BADGE_OUTLINE = "&H00E04C5B&"   # #5B4CE0 蓝紫
_BADGE_WHITE = "&H00FFFFFF&"
_BADGE_BOX = "&H00E04C5B&"       # 紫底（大字版式）
_BADGE_BADGE_BG = "&H0060B83A&"  # 黄绿标签底（#3AB860）


def build_ass_badge(lines, out_path, style=None):
    """生成"卖点标签"风格 ASS（参考片排版）。

    lines 每条可带 kind: 'tag'(默认) / 'title'(开场商品名) / 'big'(切光大字)。
    style 可带 play_w / play_h（按成片真实尺寸自适应，避免 9:16 写死导致 3:4 偏移）。
    返回 {'ok','path'}。
    """
    style = style or {}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pw = int(style.get("play_w", 720))
    ph = int(style.get("play_h", 960))
    font = style.get("font", "Microsoft YaHei")

    # 字号按画面高度比例：参考片 960 高时正文约 43px
    base = int(style.get("size") or round(ph * 0.045))
    big = round(base * 1.28)
    title = round(base * 1.10)
    # 底部留白：参考片字幕中心约在距底 75px（960 高）
    margin_v = int(style.get("margin_v") or round(ph * 0.075))
    outline = int(style.get("outline", 4))
    align = int(style.get("alignment", 2))  # 2=底部居中

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {pw}
PlayResY: {ph}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Tag,{font},{base},{_BADGE_WHITE},&H000000FF&,{_BADGE_OUTLINE},&H80000000&,-1,0,0,0,100,100,1,0,1,{outline},0,{align},20,20,{margin_v},1
Style: Title,{font},{title},{_BADGE_WHITE},&H000000FF&,{_BADGE_OUTLINE},&H80000000&,-1,0,0,0,100,100,1,0,1,{outline},0,{align},20,20,{margin_v},1
Style: Big,{font},{big},{_BADGE_WHITE},&H000000FF&,{_BADGE_BOX},{_BADGE_BOX},-1,0,0,0,100,100,2,0,3,{outline},0,{align},20,20,{margin_v},1
Style: Spark,{font},{round(base * 0.46)},{_BADGE_WHITE},&H000000FF&,{_BADGE_OUTLINE},&H80000000&,-1,0,0,0,100,100,0,0,1,3,0,2,20,20,{margin_v},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""

    events = []
    for ln in lines:
        raw = (ln.get("text") or "").strip()
        if not raw:
            continue
        kind = (ln.get("kind") or "tag").lower()
        # 装饰全部拼进可见文字（白字蓝紫描边一起生效），不依赖 \pos 定位，
        # 避免不同比例下定位漂移。override 前缀单独拼接，不走可见文本转义。
        if kind == "big":
            sty, visible, ov = "Big", f"{raw} ✦", r"{\fad(150,150)}"
        elif kind == "title":
            sty, visible, ov = "Title", f"♥ {raw} ♥ ✦", r"{\fad(150,150)}"
        else:
            sty, visible, ov = "Tag", f"♥ {raw} ♥", r"{\fad(150,150)}"
        s = ms_to_ass_time(ln.get("start_ms", 0))
        e = ms_to_ass_time(ln.get("end_ms", 0))
        events.append(f"Dialogue: 0,{s},{e},{sty},,0,0,0,,{ov}{_escape_ass(visible)}")

    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
    return {"ok": True, "path": str(out_path)}


def _ffmpeg_path_for_filter(p):
    """Windows 路径给 libass filter 用：转义盘符冒号与反斜杠。"""
    s = str(Path(p).resolve()).replace("\\", "/")
    return s.replace(":", r"\:")


def burn_subtitles(video_in, subtitle_path, out_path, style=None, enabled=True):
    """把字幕内嵌进视频。enabled=False 时原样复制视频（不做任何字幕处理）。

    返回 {'ok','path','error','enabled'}。
    """
    video_in, subtitle_path, out_path = Path(video_in), Path(subtitle_path), Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not enabled:
        # 不烧字幕：直接复制，保证画面零改动
        import shutil
        if video_in.resolve() != out_path.resolve():
            shutil.copy2(video_in, out_path)
        return {"ok": True, "path": str(out_path), "error": "", "enabled": False, "skipped": True}

    if not subtitle_path.exists():
        return {"ok": False, "error": "字幕文件不存在", "enabled": True}

    # 样式用 ASS 精确控制；SRT 只作为可导出的通用格式
    ass_path = out_path.parent / f"_burn_{out_path.stem}.ass"
    style = style or {}
    # 【阶段十】preset="selling_badge" 时走参考片卖点标签排版；
    # 其余情况（含缺省）完全走原 build_ass，行为一字不变。
    if style.get("preset") == BADGE_PRESET:
        badge_lines = style.get("lines") or _load_lines_from_srt(subtitle_path)
        # 按成片真实尺寸自适应，避免 9:16 写死造成 3:4 字幕偏移
        try:
            _p = media.probe(str(video_in))
            style = dict(style)
            style.setdefault("play_w", _p.get("width", 720))
            style.setdefault("play_h", _p.get("height", 960))
        except Exception:  # noqa: BLE001
            pass
        gen = build_ass_badge(badge_lines, ass_path, style)
    else:
        gen = build_ass(_load_lines_from_srt(subtitle_path), ass_path, style)
    if not gen["ok"]:
        return {"ok": False, "error": "ASS 字幕生成失败", "enabled": True}

    sub_arg = _ffmpeg_path_for_filter(ass_path)
    vf = f"ass='{sub_arg}'"
    args = ["-y", "-i", str(video_in), "-vf", vf,
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-an", "-movflags", "+faststart", str(out_path)]
    try:
        r = subprocess.run([media.ffmpeg_exe()] + args,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr.decode("utf-8", errors="replace").strip()[-500:],
                    "enabled": True}
        if not out_path.exists() or out_path.stat().st_size < 1000:
            return {"ok": False, "error": "烧字幕后输出为空", "enabled": True}
        return {"ok": True, "path": str(out_path), "error": "", "enabled": True}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "烧字幕超时", "enabled": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "enabled": True}
    finally:
        try:
            ass_path.unlink()
        except OSError:
            pass


def _load_lines_from_srt(path):
    """读回 SRT 用于烧录（保留用户可能手动编辑过的时间）。"""
    import re
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    lines = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for b in blocks:
        parts = b.strip().split("\n")
        if len(parts) < 3 or "-->" not in parts[1]:
            continue
        times = parts[1].split("-->")
        if len(times) != 2:
            continue
        lines.append({
            "start_ms": srt_time_to_ms(times[0].strip()),
            "end_ms": srt_time_to_ms(times[1].strip()),
            "text": " ".join(parts[2:]),
        })
    return lines


def srt_time_to_ms(s):
    m = __import__("re").match(r"(\d+):(\d+):(\d+)[,.](\d+)", s)
    if not m:
        return 0
    h, mi, sec, ms = map(int, m.groups())
    return ((h * 60 + mi) * 60 + sec) * 1000 + ms
