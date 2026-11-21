# -*- coding: utf-8 -*-
"""阶段测试用的素材路径解析（Phase C）：不再写死唯一桌面路径。

优先环境变量 MAKEMYCLIP_MEDIA_ROOT，其次常见桌面样例目录；都没有则返回 None，
调用方应 skip，而不是硬 fail。
"""
import os
from pathlib import Path


def media_root():
    env = os.environ.get("MAKEMYCLIP_MEDIA_ROOT", "").strip()
    if env and Path(env).exists():
        return Path(env)
    cand = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01"
    if cand.exists():
        return cand
    return None


def require_media_or_skip(check_fn, name="真实桌面素材"):
    """若无素材目录，记一条 skip 风格的通过说明（供自定义 check 列表使用）。"""
    root = media_root()
    if root is None:
        check_fn(f"{name}（跳过：未设置 MAKEMYCLIP_MEDIA_ROOT 且无默认样例）", True, "skipped")
        return None
    return root
