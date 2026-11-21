# -*- coding: utf-8 -*-
"""最终合成引擎（阶段五）：把画面 + 字幕 + 旁白 + 音乐合成最终 MP4。

链路：阶段四的无声成片 ->（可选）烧字幕 ->（可选）混音 -> 最终 MP4。
三轨（旁白/字幕/音乐）完全独立开关，分别关闭互不影响（任务书验收要求）。
所有中间文件放 cache，成片放 exports，绝不覆盖原始素材。
"""
from pathlib import Path

from .. import config
from . import subtitle, audio_mixer


def export_final(silent_video, lines, subtitle_path, out_path,
                 subtitle_style=None,
                 enable_subtitle=True, enable_narration=True, enable_music=True,
                 narration_path=None, music_path=None, music_volume=0.25,
                 duck=True, duration_ms=0, progress_cb=None):
    """完整合成。lines 为逐句文案（带 start_ms/end_ms/text）。

    返回 {'ok','path','error','steps':[...],'tracks':{...}}。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    steps = []
    work = config.CACHE_DIR / "final"
    work.mkdir(parents=True, exist_ok=True)
    stem = out_path.stem

    # 【阶段十】卖点标签模式：按成片真实时长精确校准字幕时间线，
    # 消除 xfade 叠化累积造成的末尾漂移；标准模式不动（回归不变）。
    # 【阶段十二】优先用 style 里已带 kind 版式的 lines（完整工作台 decorate 过），
    # 避免被函数参数里无 kind 的 lines 覆盖，导致开场商品名/切光大字退化成普通小标签。
    eff_style0 = dict(subtitle_style or {})
    if eff_style0.get("preset") == subtitle.BADGE_PRESET:
        try:
            from .. import media
            from . import narration as _nar
            _probe = media.probe(str(silent_video))
            _dur = _probe.get("duration_ms", 0)
            _base = eff_style0.get("lines") or lines
            if _dur > 0:
                _base = _nar.calibrate_to_duration(_base, _dur)
            lines = _base                    # SRT 与烧录用同一份，文字完全一致
            eff_style0["lines"] = lines
            eff_style0.setdefault("play_w", _probe.get("width", 720) or 720)
            eff_style0.setdefault("play_h", _probe.get("height", 960) or 960)
        except Exception:  # noqa: BLE001
            pass

    # 1) 字幕文件（SRT 始终生成，供用户导出；是否内嵌由开关决定）
    srt_r = subtitle.build_srt(lines, subtitle_path)
    steps.append({"step": "生成SRT", "ok": srt_r["ok"], "count": srt_r.get("count", 0)})

    # 2) 烧字幕（关闭则原样复制，保证画面零改动）
    # 【阶段十】卖点标签排版：把带 kind 的 lines 透传给排版引擎，
    # 使 SRT 导出文字与画面烧录文字完全一致（都是短标签）。
    burned = work / f"{stem}_sub.mp4"
    eff_style = eff_style0  # 已含校准后的 lines（卖点标签模式）；标准模式即原始 style
    sub_r = subtitle.burn_subtitles(silent_video, subtitle_path, burned,
                                    style=eff_style, enabled=enable_subtitle)
    if not sub_r["ok"]:
        return {"ok": False, "path": str(out_path), "error": "字幕步骤失败：" + sub_r["error"],
                "steps": steps, "tracks": {}}
    steps.append({"step": "内嵌字幕", "ok": True, "skipped": bool(sub_r.get("skipped"))})
    if progress_cb:
        progress_cb(1, 3, "字幕处理完成")

    # 3) 混音（旁白/音乐/静音 三种情况）
    mix_r = audio_mixer.mix_audio(
        burned, narration_path, music_path, out_path,
        enable_narration=enable_narration, enable_music=enable_music,
        music_volume=music_volume, duck=duck)
    if not mix_r["ok"]:
        return {"ok": False, "path": str(out_path), "error": "混音步骤失败：" + mix_r["error"],
                "steps": steps, "tracks": mix_r.get("tracks", {})}
    steps.append({"step": "混合音频", "ok": True, "tracks": mix_r["tracks"]})
    if progress_cb:
        progress_cb(2, 3, "音频混音完成")

    # 4) 校验成片
    from .video_editor import probe_output
    verify = probe_output(out_path)
    steps.append({"step": "校验成片", "ok": verify["ok"]})
    if progress_cb:
        progress_cb(3, 3, "成片校验完成")

    return {
        "ok": bool(verify["ok"]), "path": str(out_path), "error": verify.get("error", ""),
        "steps": steps, "tracks": mix_r["tracks"], "verify": verify,
        "srt_path": srt_r.get("path", ""),
    }
