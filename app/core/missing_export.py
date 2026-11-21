# -*- coding: utf-8 -*-
"""缺片 / 补拍建议导出（Phase A）。

匹配结果里已有 missing + advice；这里只做可读清单，方便拍摄对接。
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def collect_missing(match_results: dict, storyboards: Optional[List[dict]] = None) -> List[dict]:
    """从 match_all 结果抽出缺失项。"""
    sb_names = {}
    if storyboards:
        for s in storyboards:
            sb_names[str(s.get("id"))] = s.get("name") or ""
    out = []
    for sid, res in (match_results or {}).items():
        if not isinstance(res, dict):
            continue
        if not res.get("missing"):
            continue
        out.append({
            "storyboard_id": sid,
            "name": sb_names.get(str(sid)) or res.get("name") or f"分镜{sid}",
            "reason": res.get("reason") or "未找到合适素材",
            "advice": res.get("advice") or "按分镜目标补拍稳定清晰画面",
        })
    return out


def export_missing_txt(rows: List[dict], path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "MakeMyClip 缺片与补拍建议",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"缺失分镜数：{len(rows)}",
        "-" * 48,
    ]
    if not rows:
        lines.append("（当前没有标记为缺失的分镜）")
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. 【{r.get('name', '')}】")
        lines.append(f"   原因：{r.get('reason', '')}")
        lines.append(f"   补拍：{r.get('advice', '')}")
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


def export_missing_csv(rows: List[dict], path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["storyboard_id", "name", "reason", "advice"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    return str(p)


def export_missing(match_results: dict, out_dir: str, storyboards=None,
                   fmt: str = "both") -> Tuple[Optional[str], Optional[str]]:
    """导出到 out_dir，返回 (txt_path, csv_path)。"""
    rows = collect_missing(match_results, storyboards)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    txt = csv_path = None
    if fmt in ("txt", "both"):
        txt = export_missing_txt(rows, str(base / f"缺片补拍清单_{stamp}.txt"))
    if fmt in ("csv", "both"):
        csv_path = export_missing_csv(rows, str(base / f"缺片补拍清单_{stamp}.csv"))
    return txt, csv_path
