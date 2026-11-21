# -*- coding: utf-8 -*-
"""阶段 B · 图片素材支持（补齐现有程序只支持视频的缺口）

背景（代码级证据）：
  app/config.py 第 21 行 `VIDEO_EXTS` 只有 8 种视频扩展名，没有图片。
  任务书要求"支持导入图片素材；如果当前程序不支持，先补齐这项基础能力"。

本文件的做法（不修改任何老文件）：
  - 自己维护 IMAGE_EXTS，不去改 config.VIDEO_EXTS（避免影响旧界面的导入过滤）。
  - probe_image() 返回与 media.probe() **同结构**的 dict，可直接喂 db.add_asset()。
  - 图片 duration_ms 记为 0（表示静帧），界面显示"静帧"；
    将来渲染时由 target_ms 决定展示时长，避免伪造"这段视频有 3 秒"。
  - 中文路径用 np.fromfile + cv2.imdecode 读，绕开 cv2.imread 不支持中文的老问题。

已知限制（如实记录）：
  - 图片素材能导入、能显示、能进 assets 表；**当前渲染链尚不支持静帧转片段**，
    那属于阶段 D 的导出改造范围，本阶段不做，也不假装能做。
"""
import hashlib
import re
from pathlib import Path

import cv2
import numpy as np

from .. import config

# 常见图片格式（按淘宝主图/详情页实际会用到的）
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

# 将来渲染静帧时的建议默认展示时长（本阶段不生效，仅登记常量供阶段 D 使用）
IMAGE_DEFAULT_DISPLAY_MS = 3000


def is_image(path) -> bool:
    return Path(str(path)).suffix.lower() in IMAGE_EXTS


def is_supported(path) -> bool:
    """视频或图片都算可导入。"""
    ext = Path(str(path)).suffix.lower()
    return ext in config.VIDEO_EXTS or ext in IMAGE_EXTS


def _imread_unicode(path):
    """读图，支持中文路径（cv2.imread 在 Windows 对中文路径会返回 None）。"""
    p = Path(str(path))
    try:
        buf = np.fromfile(str(p), dtype=np.uint8)
        if buf.size == 0:
            return None
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:  # noqa: BLE001 - 单张图失败不能拖垮导入
        return None


def _imwrite_unicode(path, img, quality=88) -> bool:
    """写图，支持中文路径。"""
    p = Path(str(path))
    try:
        ext = p.suffix.lower() or ".jpg"
        ok, buf = cv2.imencode(ext, img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            return False
        p.parent.mkdir(parents=True, exist_ok=True)
        buf.tofile(str(p))
        return True
    except Exception:  # noqa: BLE001
        return False


def probe_image(path) -> dict:
    """探测一张图片，返回与 media.probe() 同结构的 dict。

    图片没有时长/帧率/音轨，这些字段如实置 0，不编造。
    """
    p = Path(str(path))
    result = {
        "path": str(p), "filename": p.name, "folder": str(p.parent),
        "size_bytes": p.stat().st_size if p.exists() else 0,
        "duration_ms": 0,          # 静帧，没有时长
        "width": 0, "height": 0, "fps": 0.0,
        "rotation": 0, "has_audio": 0, "decode_ok": 0, "codec": "",
        "error": "", "kind": "image",
    }
    if not p.exists():
        result["error"] = "文件不存在"
        return result
    img = _imread_unicode(p)
    if img is None:
        result["error"] = "图片无法读取（格式不支持或文件损坏）"
        return result
    h, w = img.shape[:2]
    result["width"], result["height"] = int(w), int(h)
    result["decode_ok"] = 1
    result["codec"] = p.suffix.lower().lstrip(".")
    return result


def make_image_thumb(path, width=320) -> str:
    """给图片生成缩略图，返回绝对路径；失败返回空串。"""
    p = Path(str(path))
    stem = re.sub(r"[^\w\u4e00-\u9fff-]", "_", p.stem)[:60]
    key = hashlib.md5(str(p).encode("utf-8")).hexdigest()[:10]
    out = config.THUMB_DIR / f"{stem}_{key}_img.jpg"
    if out.exists():
        return str(out)
    img = _imread_unicode(p)
    if img is None:
        return ""
    h, w = img.shape[:2]
    if w > width:
        img = cv2.resize(img, (width, max(1, int(h * width / w))), interpolation=cv2.INTER_AREA)
    return str(out) if _imwrite_unicode(out, img) else ""


def probe_any(path) -> dict:
    """统一入口：按扩展名分派到视频或图片探测。"""
    if is_image(path):
        return probe_image(path)
    from .. import media
    info = media.probe(path)
    info["kind"] = "video"
    return info


def make_thumb_any(path, duration_ms=0) -> str:
    """统一入口：按扩展名分派缩略图生成。"""
    if is_image(path):
        return make_image_thumb(path)
    from .. import media
    return media.make_thumb(path, duration_ms)


def list_importable(folder) -> list:
    """列出文件夹下所有可导入的素材（视频 + 图片），不递归。"""
    d = Path(str(folder))
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.iterdir()):
        if p.is_file() and is_supported(p):
            out.append(str(p))
    return out
