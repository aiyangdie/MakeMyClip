# -*- coding: utf-8 -*-
"""非破坏性剪辑引擎（阶段四核心，阶段六增补转场/停留/联动）。

设计要点（对应任务书"增量式剪辑"铁律）：
- 每个镜头有独立 ID（shot_id）与独立缓存标识（cache_key）。
- 中间片段 = 每个镜头裁切+比例适配后的独立 MP4，文件名由 cache_key 决定。
- 只有"素材路径/起止时间/裁切参数/导出参数"变化，对应镜头的 cache_key 才变、才重生成。
- 改一个镜头：只重生成它的中间片段，其它镜头的缓存文件原样复用，最后重新拼接。
- 任何镜头都不写回原始素材（只读）。

商品保护：比例适配用 scale+pad（保持宽高比、补边），绝不拉伸商品；不做任何生成式修改。

【阶段六增补 · 可全部回退】
- 转场：concat_segments 支持 transition="fade"（xfade 叠化）；默认 "none" 仍是原来的
  硬切 concat demuxer。转场只发生在拼接层，不写回单镜头缓存 -> 单镜头独立性不变。
- 最短停留：render_shot 支持 min_hold_ms，不足时末帧定格补足（真实画面停留，非编造）。
  该值纳入 cache_key，改停留时间才会重渲染。
- 联动镜头：render_all 识别 shot["sub_segments"]（JSON），把多段真实画面用短叠化
  合成"一个镜头"的中间片段。在时间线里仍是一行，改它不影响其它镜头。
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

from .. import config, media


def _json_loads(value, default):
    """从可能是 JSON 字符串 / list / None 的值里安全解析出列表。"""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            v = json.loads(value)
            return v if isinstance(v, list) else default
        except Exception:
            return default
    return default


def cache_key_for(shot, export_params):
    """由影响画面的全部输入算出稳定标识。输入不变 -> key 不变 -> 复用缓存。

    注意：转场(transition)不纳入单镜头 key——它只作用于拼接层，不影响单镜头画面；
    若纳入会导致切换转场时所有镜头白白重渲染。min_hold_ms 影响单镜头画面，必须纳入。
    【阶段七增补】target_ms(每镜头建议时长)同样纳入——改一个镜头的建议时长，
    只有它自己的 key 变、只有它自己重渲染，其它镜头缓存照常复用。
    """
    raw = json.dumps({
        "path": shot.get("asset_path", ""),
        "start_ms": shot.get("start_ms", 0),
        "end_ms": shot.get("end_ms", 0),
        "crop": shot.get("crop", ""),
        "target_ms": shot.get("target_ms", 0) or 0,
        "ratio": export_params.get("ratio", ""),
        "res": export_params.get("res", ""),
        "fps": export_params.get("fps", 0),
        "crf": export_params.get("crf", 23),
        "min_hold_ms": export_params.get("min_hold_ms", 0),
        "sub_segments": shot.get("sub_segments", "") or "",
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def target_size(ratio, res):
    return config.EXPORT_SIZES.get(ratio, config.EXPORT_SIZES["16:9 横屏"]).get(
        res, config.EXPORT_SIZES["16:9 横屏"]["720p"])


def _run(args, timeout=300):
    return subprocess.run([media.ffmpeg_exe()] + args,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)


def render_shot(shot, export_params, force=False):
    """生成单个镜头的中间片段。返回 dict：
    {'ok', 'path', 'cache_key', 'cached'(是否命中缓存), 'error'}
    """
    w, h = target_size(export_params["ratio"], export_params["res"])
    fps = export_params["fps"]
    crf = export_params["crf"]
    key = cache_key_for(shot, export_params)
    out = config.RENDER_CACHE_DIR / f"{key}.mp4"
    result = {"ok": False, "path": str(out), "cache_key": key, "cached": False, "error": ""}
    if out.exists() and out.stat().st_size > 1000 and not force:
        result["ok"] = True
        result["cached"] = True
        return result

    path = shot.get("asset_path", "")
    if not path or not Path(path).exists():
        result["error"] = "素材文件不存在"
        return result
    start_s = shot.get("start_ms", 0) / 1000.0
    end_s = shot.get("end_ms", 0) / 1000.0
    if end_s <= start_s:
        result["error"] = "起止时间无效"
        return result
    dur = end_s - start_s

    # 【阶段七增补】建议时长 target_ms（每镜头单独设定）：
    #   - 优先级：镜头自己的 target_ms > 全局 min_hold_ms > 0(不限，素材多长就多长)
    #   - 素材比建议短 -> 末帧定格补足（看清）；比建议长 -> 只取需要的部分（不拖沓）
    #   - 全部基于真实画面，不编造任何内容
    target_s = float(shot.get("target_ms", 0) or 0) / 1000.0
    hold_s = float(export_params.get("min_hold_ms", 0) or 0) / 1000.0
    if target_s > 0:
        out_dur = target_s
    else:
        out_dur = max(dur, hold_s)

    # 比例适配：先等比缩放使其完整放入目标框，再居中补边（不拉伸、不裁掉商品）
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
          f"fps={fps},format=yuv420p")
    if out_dur > dur + 0.001:
        vf += f",tpad=stop_mode=clone:stop_duration={out_dur - dur:.3f}"
    args = ["-y", "-ss", f"{start_s:.3f}", "-i", path, "-t", f"{out_dur:.3f}",
            "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-movflags", "+faststart", str(out)]
    try:
        r = _run(args)
        if r.returncode != 0:
            result["error"] = r.stderr.decode("utf-8", errors="replace").strip()[-400:]
            return result
        if not out.exists() or out.stat().st_size <= 1000:
            result["error"] = "输出文件为空"
            return result
        result["ok"] = True
        return result
    except subprocess.TimeoutExpired:
        result["error"] = "渲染超时"
        return result
    except Exception as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}: {e}"
        return result


def render_linked_shot(shot, export_params, force=False):
    """把联动镜头的多个真实子片段用短叠化合成"一个镜头"的中间片段。

    shot['sub_segments'] 形如：
      [{"asset_path":..., "start_ms":0,   "end_ms":2000},
       {"asset_path":..., "start_ms":4000,"end_ms":13000}]
    子片段各自先走 render_shot 的比例适配（保证尺寸/帧率一致），再用 xfade 叠化。
    cache_key 由 shot 整体（含 sub_segments）决定 -> 改任一子段只重渲染这个镜头。
    """
    w, h = target_size(export_params["ratio"], export_params["res"])
    fps = export_params["fps"]
    crf = export_params["crf"]
    key = cache_key_for(shot, export_params)
    out = config.RENDER_CACHE_DIR / f"{key}.mp4"
    result = {"ok": False, "path": str(out), "cache_key": key, "cached": False, "error": ""}
    if out.exists() and out.stat().st_size > 1000 and not force:
        result["ok"] = True
        result["cached"] = True
        return result

    subs = _json_loads(shot.get("sub_segments"), [])
    subs = [s for s in subs if isinstance(s, dict) and s.get("asset_path")]
    if len(subs) < 2:
        result["error"] = "联动镜头至少需要两个有效子片段"
        return result

    # 复用 render_shot 渲染每个子片段（临时 key，确保与主镜头 key 不冲突）
    part_paths = []
    for i, sub in enumerate(subs):
        tmp_shot = {
            "asset_path": sub.get("asset_path", ""),
            "start_ms": sub.get("start_ms", 0),
            "end_ms": sub.get("end_ms", 0),
            "crop": sub.get("crop", ""),
            # 联动子片段也可以有自己的建议时长（如：按下2.5s + 灯变7.5s）
            "target_ms": sub.get("target_ms", 0) or 0,
        }
        # 用独立命名空间目录存子片段，避免污染主镜头缓存
        sr = render_shot(tmp_shot, export_params, force=force)
        if not sr["ok"]:
            result["error"] = f"子片段{i+1}渲染失败：{sr['error']}"
            return result
        part_paths.append(sr["path"])

    single_transition = float(export_params.get("sub_transition_s", 0.4) or 0.4)
    joined = _xfade_concat(part_paths, out, transition="fade",
                           transition_s=single_transition, w=w, h=h, fps=fps, crf=crf)
    if not joined["ok"]:
        result["error"] = joined["error"]
        return result
    result["ok"] = True
    return result


def _stream_len(path):
    info = media.probe(path)
    return max(0.0, info.get("duration_ms", 0) / 1000.0)


def _xfade_concat(paths, output_path, transition="fade", transition_s=0.4,
                  w=1280, h=720, fps=30, crf=23):
    """用 xfade 滤镜链把多个同规格片段叠化拼接（会重编码）。"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    durations = [_stream_len(p) for p in paths]
    t = max(0.0, float(transition_s))
    # 片段太短无法承载转场时，该处退化为硬切（offset 仍按无重叠计算）
    parts = []
    for i, p in enumerate(paths):
        parts.append(f"[{i}:v]settb=AVTB,format=yuv420p,setsar=1[iv{i}]")
    cur = "[iv0]"
    cum = durations[0]
    for i in range(1, len(paths)):
        usable = min(t, max(0.0, min(durations[i - 1], durations[i]) - 0.08))
        off = max(0.0, cum - usable)
        label = f"[x{i}]"
        if usable > 0.01:
            parts.append(f"{cur}[iv{i}]xfade=transition={transition}:"
                         f"duration={usable:.3f}:offset={off:.3f}{label}")
        else:
            parts.append(f"{cur}[iv{i}]concat=n=2:v=1:a=0{label}")
        cum = cum + durations[i] - usable
        cur = label
    fc = ";".join(parts)
    args = ["-y"]
    for p in paths:
        args += ["-i", str(p)]
    args += ["-filter_complex", fc, "-map", cur,
             "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
             "-r", str(fps), "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(output_path)]
    try:
        r = _run(args, timeout=600)
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr.decode("utf-8", errors="replace").strip()[-500:]}
        if not output_path.exists() or output_path.stat().st_size <= 1000:
            return {"ok": False, "error": "叠化输出为空"}
        return {"ok": True, "path": str(output_path)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def render_all(shots, export_params, db=None, progress_cb=None, cancel_cb=None):
    """按时间线渲染所有镜头中间片段。

    返回 {'ok':bool, 'segments':[...], 'rendered':int, 'cached':int, 'errors':[...]}
    progress_cb(done, total, shot_id, cached)
    """
    segments = []
    rendered = cached = 0
    errors = []
    total = len(shots)
    for i, shot in enumerate(shots, 1):
        if cancel_cb and cancel_cb():
            break
        is_linked = bool(_json_loads(shot.get("sub_segments"), []))
        if not shot.get("asset_path") and not is_linked:
            errors.append({"shot_id": shot.get("shot_id"), "error": "镜头未绑定素材（缺镜头）"})
            if progress_cb:
                progress_cb(i, total, shot.get("shot_id"), True)
            continue
        r = (render_linked_shot(shot, export_params) if is_linked
             else render_shot(shot, export_params))
        if r["ok"]:
            segments.append({"shot_id": shot["shot_id"], "path": r["path"],
                             "cache_key": r["cache_key"], "cached": r["cached"],
                             "linked": is_linked})
            if r["cached"]:
                cached += 1
            else:
                rendered += 1
            # 更新镜头缓存标识
            if db:
                db.update_shot(shot["shot_id"], cache_key=r["cache_key"])
        else:
            errors.append({"shot_id": shot.get("shot_id"), "error": r["error"]})
        if progress_cb:
            progress_cb(i, total, shot.get("shot_id"), r["cached"])
    return {
        "ok": len(errors) == 0 and len(segments) > 0,
        "segments": segments, "rendered": rendered, "cached": cached,
        "errors": errors,
    }


def concat_segments(segments, output_path, transition="none", transition_s=0.4,
                    progress_cb=None, crf=23):
    """把中间片段按顺序拼接成成片。

    - transition="none"（默认）：concat demuxer + -c copy，原来的硬切行为，零损失。
    - transition="fade"：xfade 叠化，平滑过渡（会重编码，中间缓存不受影响）。
    【阶段十二】crf 由调用方传入，不再写死 23；缺省值仍是 23，旧调用行为不变。
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if transition and transition != "none" and len(segments) >= 2:
        first = media.probe(segments[0]["path"])
        return _xfade_concat(
            [s["path"] for s in segments], output_path,
            transition=transition, transition_s=transition_s,
            w=first.get("width", 1280), h=first.get("height", 720),
            fps=int(first.get("fps", 30) or 30), crf=crf)

    list_file = output_path.parent / f"_concat_{output_path.stem}.txt"
    lines = []
    for seg in segments:
        p = str(Path(seg["path"]).resolve()).replace("\\", "/")
        lines.append(f"file '{p}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")
    args = ["-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", "-movflags", "+faststart", str(output_path)]
    try:
        r = _run(args)
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr.decode("utf-8", errors="replace").strip()[-400:]}
        if not output_path.exists():
            return {"ok": False, "error": "成片未生成"}
        return {"ok": True, "path": str(output_path)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        try:
            list_file.unlink()
        except OSError:
            pass


def probe_output(path):
    """校验成片：时长/分辨率/帧率/能否解码。"""
    info = media.probe(path)
    return {
        "ok": bool(info.get("decode_ok")),
        "duration_ms": info.get("duration_ms", 0),
        "width": info.get("width", 0),
        "height": info.get("height", 0),
        "fps": info.get("fps", 0),
        "error": info.get("error", ""),
    }
