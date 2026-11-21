# -*- coding: utf-8 -*-
"""旁白 / 音乐混音（阶段五）。

功能：
- 旁白轨：把逐句配音 WAV 按镜头时间摆到时间轴（adelay + amix）。
- 音乐轨：导入用户自有音乐、音量、淡入淡出、裁切到视频长度。
- 旁白出现时自动降低音乐（sidechaincompress，环境已验证滤镜可用）。
- 三轨独立开关：旁白/字幕/音乐可分别关闭，互不影响。
- 默认不使用任何授权不明的音乐——没有用户导入的音乐就不产生音乐轨。

商品保护：音频处理不改动商品画面，也不改动原始素材文件。
"""
import subprocess
from pathlib import Path

from .. import config, media


def _run(args, timeout=600):
    return subprocess.run([media.ffmpeg_exe()] + args,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)


def build_narration_track(voices, duration_ms, out_path, volume=1.0):
    """把 [(wav_path, start_ms), ...] 摆到时间轴，合成一条完整旁白轨。

    采用两步法（绕开 FFmpeg 9 中 amix(duration=longest) 输入>=4 时
    apad=whole_dur 补静音失效的坑）：
      第一步：只把各句按时间混音，输出原始长度。
      第二步：混入一条等长的 lavfi 静音源，保证输出精确覆盖视频全长。
    out_path 为 .wav；返回 {'ok','path','error'}。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    voices = [(p, ms) for p, ms in (voices or []) if p and Path(p).exists()]
    if not voices:
        return {"ok": False, "error": "无可用配音", "empty": True}
    dur_s = max(0.1, duration_ms / 1000.0)

    # 第一步：各句按 start_ms 摆到时间轴混音
    filters = []
    for i, (p, start_ms) in enumerate(voices):
        filters.append(f"[{i}:a]adelay={int(max(0, start_ms))}:all=1[a{i}]")
    mix_inputs = "".join(f"[a{i}]" for i in range(len(voices)))
    filters.append(f"{mix_inputs}amix=inputs={len(voices)}:duration=longest:"
                   f"dropout_transition=0,volume={volume}[mixed]")
    tmp = out_path.parent / f"_nar_mix_{out_path.stem}.wav"
    args = []
    for p, _ in voices:
        args += ["-i", str(p)]
    args += ["-filter_complex", ";".join(filters), "-map", "[mixed]",
             "-c:a", "pcm_s16le", "-y", str(tmp)]
    try:
        r = _run(args)
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr.decode("utf-8", errors="replace").strip()[-500:]}
        # 第二步：混入等长静音源，保证输出精确为 dur_s（不依赖 amix 的时长判断）
        silent_src = f"anullsrc=channel_layout=stereo:sample_rate=44100"
        args2 = ["-y", "-i", str(tmp), "-f", "lavfi", "-t", f"{dur_s:.3f}",
                 "-i", silent_src,
                 "-filter_complex",
                 "[0:a]asetpts=PTS-STARTPTS[n];[n][1:a]amix=inputs=2:duration=longest:"
                 "weights='1 0',atrim=0:" + f"{dur_s:.3f}" + "[out]",
                 "-map", "[out]", "-t", f"{dur_s:.3f}", "-c:a", "pcm_s16le", str(out_path)]
        r2 = _run(args2)
        if r2.returncode != 0:
            return {"ok": False, "error": r2.stderr.decode("utf-8", errors="replace").strip()[-500:]}
        if not out_path.exists() or out_path.stat().st_size < 500:
            return {"ok": False, "error": "旁白轨为空"}
        return {"ok": True, "path": str(out_path), "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def prepare_music(music_path, duration_ms, out_path, volume=0.3, fade_in=1.0, fade_out=2.0):
    """把用户音乐裁到视频长度 + 音量 + 淡入淡出。返回 {'ok','path','error'}。"""
    music_path = Path(music_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not music_path.exists():
        return {"ok": False, "error": "音乐文件不存在"}
    dur_s = max(0.5, duration_ms / 1000.0)
    fo_start = max(0.0, dur_s - fade_out)
    af = (f"atrim=0:{dur_s:.3f},asetpts=PTS-STARTPTS,volume={volume},"
          f"afade=t=in:st=0:d={fade_in:.2f},afade=t=out:st={fo_start:.2f}:d={fade_out:.2f}")
    args = ["-y", "-i", str(music_path), "-af", af, "-t", f"{dur_s:.3f}",
            "-c:a", "pcm_s16le", str(out_path)]
    try:
        r = _run(args)
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr.decode("utf-8", errors="replace").strip()[-500:]}
        return {"ok": True, "path": str(out_path), "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def mix_audio(video_path, narration_path, music_path, out_path,
              enable_narration=True, enable_music=True,
              music_volume=0.25, duck=True, duration_ms=0):
    """把旁白和/或音乐混入视频，生成带音轨的 MP4。

    duck=True 且旁白存在时：旁白作为 sidechain，音乐在旁白处自动压低（约 -14dB）。
    返回 {'ok','path','error','tracks':{'narration':bool,'music':bool,'duck':bool}}
    """
    video_path, out_path = Path(video_path), Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    use_nar = bool(enable_narration and narration_path and Path(narration_path).exists())
    use_mus = bool(enable_music and music_path and Path(music_path).exists())
    tracks = {"narration": use_nar, "music": use_mus, "duck": False}

    if not use_nar and not use_mus:
        # 三轨全关：静音输出（不直接 copy，保证输出有静音音轨，音画同步）
        args = ["-y", "-i", str(video_path), "-f", "lavfi", "-t", "9999",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                "-shortest", "-movflags", "+faststart", str(out_path)]
        r = _run(args)
        ok = r.returncode == 0 and out_path.exists()
        return {"ok": ok, "path": str(out_path),
                "error": "" if ok else r.stderr.decode("utf-8", errors="replace").strip()[-400:],
                "tracks": tracks}

    args = ["-y", "-i", str(video_path)]
    if use_nar:
        args += ["-i", str(narration_path)]
    if use_mus:
        args += ["-i", str(music_path)]

    if use_nar and use_mus and duck:
        # [1:a]=旁白, [2:a]=音乐。音乐经 sidechain 压缩后与旁白混合。
        filters = [
            "[1:a]asplit=2[nar_out][nar_key]",
            f"[2:a]volume={music_volume}[mus]",
            "[mus][nar_key]sidechaincompress=threshold=0.03:ratio=6:"
            "attack=20:release=400[mus_duck]",
            "[nar_out][mus_duck]amix=inputs=2:duration=first:"
            "weights='1 0.9',alimiter=limit=0.95[aout]",
        ]
        tracks["duck"] = True
    elif use_nar and use_mus:
        filters = [
            f"[2:a]volume={music_volume}[mus]",
            "[1:a][mus]amix=inputs=2:duration=first:weights='1 0.9',"
            "alimiter=limit=0.95[aout]",
        ]
    elif use_nar:
        filters = ["[1:a]alimiter=limit=0.95[aout]"]
    else:
        filters = [f"[1:a]volume={music_volume},alimiter=limit=0.95[aout]"]

    # 关键修复：音频轨必须补齐到视频全长，否则 -shortest 会用较短的旁白把视频截断。
    # 取视频真实时长，把混音结果 apad 后 atrim 到该长度，并以视频时长为准输出。
    vid_dur = duration_ms / 1000.0 if duration_ms else 0
    if not vid_dur:
        info = media.probe(str(video_path))
        vid_dur = (info.get("duration_ms") or 0) / 1000.0
    if vid_dur > 0:
        # asetpts 归零时间戳后 apad=whole_dur 补齐 + atrim 截断（长音乐才不会撑长成片）。
        filters[-1] = filters[-1].replace(
            "[aout]", f",asetpts=PTS-STARTPTS,apad=whole_dur={vid_dur:.3f},"
                      f"atrim=0:{vid_dur:.3f}[aout]")

    args += ["-filter_complex", ";".join(filters),
             "-map", "0:v:0", "-map", "[aout]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(out_path)]
    if vid_dur > 0:
        args += ["-t", f"{vid_dur:.3f}"]
    try:
        r = _run(args)
        if r.returncode != 0:
            return {"ok": False, "path": str(out_path),
                    "error": r.stderr.decode("utf-8", errors="replace").strip()[-600:],
                    "tracks": tracks}
        if not out_path.exists() or out_path.stat().st_size < 1000:
            return {"ok": False, "path": str(out_path), "error": "混音输出为空", "tracks": tracks}
        return {"ok": True, "path": str(out_path), "error": "", "tracks": tracks}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "path": str(out_path),
                "error": f"{type(e).__name__}: {e}", "tracks": tracks}
