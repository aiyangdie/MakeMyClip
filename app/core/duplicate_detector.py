# -*- coding: utf-8 -*-
"""重复素材检测（阶段二）。

区分两类重复，不删任何原始文件（计划书 4.3 / 测试三）：
1. 文件完全重复：MD5 哈希一致。
2. 画面高度相似：对抽出的关键帧算感知哈希(dHash)，汉明距离判断相似。

结果分组展示，由用户决定保留哪个版本。
"""
import hashlib
from pathlib import Path

import cv2
import numpy as np

from .. import media


def file_md5(path, chunk=1024 * 1024):
    """文件 MD5；失败返回空串。"""
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(chunk)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except Exception:  # noqa: BLE001
        return ""


def dhash(path, hash_size=16):
    """感知哈希：抽中间两帧算差值哈希，返回 bit 串；失败返回空串。"""
    proxy = media.preview_link(path)
    cap = cv2.VideoCapture(proxy)
    if not cap.isOpened():
        return ""
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    bits = []
    for frac in (0.3, 0.6):
        idx = int(total * frac)
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(cv2.resize(frame, (hash_size + 1, hash_size)), cv2.COLOR_BGR2GRAY)
        diff = gray[:, 1:] > gray[:, :-1]
        bits.extend(diff.flatten().tolist())
    cap.release()
    if not bits:
        return ""
    return "".join("1" if b else "0" for b in bits)


def hamming(a, b):
    """两个等长 bit 串的汉明距离；长度不等返回 999。"""
    if not a or not b or len(a) != len(b):
        return 999
    return sum(1 for x, y in zip(a, b) if x != y)


def detect(assets, phash_threshold=6):
    """对素材列表做重复检测。

    Args:
        assets: db.get_assets() 返回的 dict 列表
        phash_threshold: 汉明距离阈值（<= 视为画面高度相似）

    Returns:
        {
          'exact_groups': [[asset_dict,...], ...],   # MD5 完全相同
          'similar_groups': [[asset_dict,...], ...], # 画面高度相似
          'details': {path: {'md5','dhash'}}
        }
    """
    details = {}
    for a in assets:
        p = a["path"]
        details[p] = {"md5": file_md5(p), "dhash": dhash(p)}

    # 完全重复分组
    md5_map = {}
    for a in assets:
        m = details[a["path"]]["md5"]
        if m:
            md5_map.setdefault(m, []).append(a)
    exact_groups = [g for g in md5_map.values() if len(g) > 1]

    # 相似分组（并查集）
    n = len(assets)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i in range(n):
        for j in range(i + 1, n):
            # MD5 已判定完全重复的，跳过感知哈希比较
            mi, mj = details[assets[i]["path"]]["md5"], details[assets[j]["path"]]["md5"]
            if mi and mi == mj:
                union(i, j)
                continue
            hi, hj = details[assets[i]["path"]]["dhash"], details[assets[j]["path"]]["dhash"]
            if hamming(hi, hj) <= phash_threshold:
                union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(assets[i])
    similar_groups = []
    for g in groups.values():
        if len(g) > 1:
            # 排除已经完全相同的组（这些在 exact 里展示）
            hashes = {details[a["path"]]["md5"] for a in g}
            if not (len(hashes) == 1 and "" not in hashes):
                similar_groups.append(g)

    return {"exact_groups": exact_groups, "similar_groups": similar_groups, "details": details}
