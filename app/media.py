# -*- coding: utf-8 -*-
"""视频读取：元数据探测、解码检测、缩略图。

第一阶段的"视频索引"能力（任务书计划书02第一层）：
- 时长、分辨率、帧率、编码、音轨、旋转角、文件大小
- 解码是否成功（失败只记录错误，不让批处理崩溃）
- 缩略图抽取

采用 imageio-ffmpeg 内置的 ffmpeg.exe，通过子进程按参数列表调用，
可正确处理中文文件名（不用 shell 字符串拼接）。
"""
import subprocess
import re
import os
import hashlib
from pathlib import Path

from . import config

_PREVIEW_DIR = config.CACHE_DIR / "preview"
_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

_ffmpeg_exe = None


def ffmpeg_exe() -> str:
    global _ffmpeg_exe
    if _ffmpeg_exe is None:
        import imageio_ffmpeg
        _ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    return _ffmpeg_exe


def _run(args, timeout=120):
    return subprocess.run(
        [ffmpeg_exe()] + args,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=timeout,
    )


def _parse_duration(text):
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not m:
        return 0
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return int((h * 3600 + mi * 60 + s) * 1000)


def probe(path):
    """探测单个视频，返回元数据 dict。永不抛异常，错误写进 result['error']。"""
    p = Path(path)
    result = {
        "path": str(p), "filename": p.name, "folder": str(p.parent),
        "size_bytes": p.stat().st_size if p.exists() else 0,
        "duration_ms": 0, "width": 0, "height": 0, "fps": 0.0,
        "rotation": 0, "has_audio": 0, "decode_ok": 0, "codec": "", "error": "",
    }
    if not p.exists():
        result["error"] = "文件不存在"
        return result
    try:
        r = _run(["-hide_banner", "-i", str(p)], timeout=30)
        text = r.stderr.decode("utf-8", errors="replace")
        result["duration_ms"] = _parse_duration(text)

        vm = re.search(r"Video:\s*([^,\n]+).*?(\d{2,5})x(\d{2,5})", text)
        if vm:
            result["codec"] = vm.group(1).strip()
            result["width"] = int(vm.group(2))
            result["height"] = int(vm.group(3))
        fm = re.search(r"(\d+(?:\.\d+)?)\s*fps", text)
        if fm:
            result["fps"] = float(fm.group(1))
        result["has_audio"] = 1 if re.search(r"Audio:\s", text) else 0
        rm = re.search(r"rotation of (-?\d+)", text) or re.search(r"rotate\s*:\s*(-?\d+)", text)
        if rm:
            result["rotation"] = int(rm.group(1)) % 360

        # 解码检测：解码开头 1 秒到空输出，只看能否成功
        d = _run(["-v", "error", "-i", str(p), "-t", "1", "-f", "null", "-"], timeout=60)
        result["decode_ok"] = 1 if d.returncode == 0 else 0
        if d.returncode != 0:
            result["error"] = d.stderr.decode("utf-8", errors="replace").strip()[:300]
        if result["duration_ms"] == 0 and not result["error"]:
            result["error"] = "未读到时长，可能不是有效视频"
    except subprocess.TimeoutExpired:
        result["error"] = "探测超时"
    except Exception as e:  # noqa: BLE001 - 单文件失败不能拖垮批处理
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def make_thumb(path, duration_ms=0, width=320):
    """抽一张缩略图，返回绝对路径；失败返回空字符串。"""
    p = Path(path)
    stem = re.sub(r"[^\w\u4e00-\u9fff-]", "_", p.stem)[:60]
    out = config.THUMB_DIR / f"{stem}_{abs(hash(str(p))) % 100000}.jpg"
    if out.exists():
        return str(out)
    seek = "1" if duration_ms < 1000 else "2"
    try:
        r = _run(["-y", "-ss", seek, "-i", str(p), "-frames:v", "1",
                  "-vf", f"scale={width}:-2", "-q:v", "4", str(out)], timeout=90)
        return str(out) if r.returncode == 0 and out.exists() else ""
    except Exception:  # noqa: BLE001
        return ""


def format_duration(ms):
    if not ms:
        return "--:--"
    s = int(ms) // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


def extract_keyframes(path, duration_ms=0, interval_sec=2.0, max_frames=12, width=480):
    """按时间间隔抽取关键帧（阶段一验收项）。

    返回 [{'time_ms':int,'path':str}, ...]。间隔由 duration 与 max_frames 共同约束，
    避免长视频抽太多帧。抽帧失败只跳过该点，不让整体崩溃。
    """
    p = Path(path)
    key = hashlib.md5(str(p).encode("utf-8")).hexdigest()[:12]
    outdir = config.CACHE_DIR / "keyframes" / key
    outdir.mkdir(parents=True, exist_ok=True)
    if duration_ms <= 0:
        info = probe(path)
        duration_ms = info.get("duration_ms", 0)
    if duration_ms <= 0:
        return []

    dur_s = duration_ms / 1000.0
    count = min(max_frames, max(1, int(dur_s / interval_sec) + 1))
    step = dur_s / count
    frames = []
    for i in range(count):
        t = step * i + step * 0.3          # 取每个区间靠前一点，避开结尾黑帧
        t = min(t, max(0, dur_s - 0.1))
        out = outdir / f"kf_{i:03d}_{int(t*1000)}ms.jpg"
        if not out.exists():
            try:
                r = _run(["-y", "-ss", f"{t:.3f}", "-i", str(p), "-frames:v", "1",
                          "-vf", f"scale={width}:-2", "-q:v", "4", str(out)], timeout=60)
                if r.returncode != 0 or not out.exists():
                    continue
            except Exception:  # noqa: BLE001
                continue
        frames.append({"time_ms": int(t * 1000), "path": str(out)})
    return frames


def preview_link(path):
    """OpenCV 在 Windows 读不了中文路径，这里用英文名硬链接/副本做代理。

    硬链接优先（不占额外空间、内容与原件一致、原件仍只读）；
    跨磁盘等硬链接失败时退回复制。返回可安全交给 cv2 的 ASCII 路径。
    """
    p = Path(path)
    if not p.exists():
        return str(p)
    key = hashlib.md5(str(p).encode("utf-8")).hexdigest()[:16]
    ext = p.suffix.lower() or ".mp4"
    target = _PREVIEW_DIR / f"{key}{ext}"
    if not target.exists() or target.stat().st_size != p.stat().st_size:
        try:
            os.link(p, target)          # 硬链接：不复制、不改动原始素材
        except OSError:
            import shutil
            shutil.copy2(p, target)     # 退回复制
    return str(target)
