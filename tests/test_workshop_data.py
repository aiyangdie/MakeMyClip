# -*- coding: utf-8 -*-
"""阶段 B · 数据适配层测试（纯逻辑，无 GUI）

覆盖：
  1. 五态派生（含边界组合）
  2. 图片素材探测（真实造图，含中文路径/webp/大写扩展名）
  3. 空项目
  4. 异常素材（decode_ok=0 / 分析失败）
  5. 分组派生
  6. 统计计算
  7. **只读性**：load_project 不得写库

运行：从项目根目录 `.venv/Scripts/python.exe tests/test_workshop_data.py`
（本文件用 __file__ 定位根目录，从任何目录跑都行）
"""
import json
import sqlite3
import sys
import tempfile
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import cv2

from app.db import ProjectDB
from app.workshop_data import bridge, image_support as img
from app.workshop_data import models as M

checks = []


def ck(name, cond, detail=""):
    checks.append({"name": name, "ok": bool(cond), "detail": str(detail)})


def _mk_asset(db, path, status="未分析", decode_ok=1, dur=5000, w=1280, h=720,
              filename=None):
    """造一条素材。

    注意：db.add_asset() 只接受 15 个基础字段，**不含 analysis_status**
    （见 app/db.py 的 cols 元组）。所以要设分析状态必须再调
    update_asset_analysis_fields()。这是本测试踩到的真实约束。
    """
    aid = db.add_asset({
        "path": str(path), "filename": filename or Path(str(path)).name,
        "folder": str(Path(str(path)).parent), "size_bytes": 1000,
        "duration_ms": dur, "width": w, "height": h, "fps": 30.0,
        "rotation": 0, "has_audio": 1, "decode_ok": decode_ok,
        "codec": "h264", "error": "" if decode_ok else "decode failed",
        "thumb_path": "", "import_time": "",
    })
    if status and status != "未分析":
        db.update_asset_analysis_fields(aid, analysis_status=status)
    return aid


def main():
    tmp = Path(tempfile.mkdtemp(prefix="mmc_ws_test_"))
    db_path = tmp / "t.db"
    db = ProjectDB(db_path)

    # ================= 1. 五态派生 =================
    a_un = _mk_asset(db, tmp / "未分析.mov", status="未分析")
    a_ms = _mk_asset(db, tmp / "已分析无待核验.mov", status="已分析")
    a_cf = _mk_asset(db, tmp / "已分析有待核验.mov", status="已分析")
    a_bad = _mk_asset(db, tmp / "读取失败.mov", status="未分析", decode_ok=0)
    a_fail = _mk_asset(db, tmp / "分析失败.mov", status="分析失败")

    # 给 a_cf 造一条待核验 clip
    db.add_clip({"asset_id": a_cf, "start_ms": 0, "end_ms": 2000,
                 "primary_tag": "", "confidence": 0.5, "score_text": "",
                 "recommend_reason": "", "potential_issue": "",
                 "verify_state": "待核验", "source": "auto_scene",
                 "keyframe_paths": "[]", "cut_reason": "test", "shot_index": 1,
                 "analysis_status": "候选待核验"})

    pv = bridge.load_project(db, db_path)
    by_id = {a.asset_id: a for a in pv.assets}

    ck("未分析素材 → 未分析", by_id[a_un].status == M.ST_UNANALYZED, by_id[a_un].status)
    ck("已分析且无待核验 → 已完成基础测量",
       by_id[a_ms].status == M.ST_MEASURED, by_id[a_ms].status)
    ck("已分析且有'待核验'clip → 待人工确认",
       by_id[a_cf].status == M.ST_CONFIRM, by_id[a_cf].status)
    ck("待确认素材的 pending_count = 1", by_id[a_cf].pending_count == 1,
       by_id[a_cf].pending_count)
    ck("decode_ok=0 且未分析 → 分析失败",
       by_id[a_bad].status == M.ST_FAILED, by_id[a_bad].status)
    ck("analysis_status='分析失败' → 分析失败",
       by_id[a_fail].status == M.ST_FAILED, by_id[a_fail].status)
    ck("失败素材有可读的错误说明", bool(by_id[a_bad].note), by_id[a_bad].note)

    # ================= 2. 分析来源必须如实 =================
    ck("已分析素材的来源 = heuristic（不得写成 vlm/cloud）",
       by_id[a_ms].analyzer_kind == "heuristic", by_id[a_ms].analyzer_kind)
    ck("未分析素材来源为空", by_id[a_un].analyzer_kind == "", by_id[a_un].analyzer_kind)
    ck("来源说明含'非 AI 理解'字样（防冒充）",
       "非 AI 理解" in by_id[a_ms].analyzer_label, by_id[a_ms].analyzer_label)

    # ================= 3. 统计 =================
    st = pv.stats
    ck("统计总数 = 5", st.total == 5, st.total)
    # 5 条素材：未分析1 + 已测量1 + 待确认1 + 失败2 → 已分析 = 测量1 + 待确认1 = 2
    ck("已分析数 = 已测量1 + 待确认1 = 2", st.analyzed == 2, st.analyzed)
    ck("待确认为 1", st.confirm == 1, st.confirm)
    ck("失败为 2", st.failed == 2, st.failed)
    ck("进度百分比 = 2/5 = 40%", st.progress_pct == 40, st.progress_pct)

    # ================= 4. 分组 =================
    ck("分组第一项是'全部'且计数正确",
       pv.groups[0].name == "全部" and pv.groups[0].count == 5,
       f"{pv.groups[0].name}/{pv.groups[0].count}")

    # ================= 5. 图片素材支持 =================
    cases = [("测试图_白底.png", 900, 1200), ("detail photo.jpg", 600, 800),
             ("大写扩展.PNG", 300, 300)]
    for name, w, h in cases:
        arr = np.full((h, w, 3), 210, np.uint8)
        cv2.rectangle(arr, (10, 10), (w - 10, h - 10), (100, 120, 190), -1)
        p = tmp / name
        ok, buf = cv2.imencode(p.suffix.lower(), arr)
        buf.tofile(str(p))

    r1 = img.probe_image(tmp / "测试图_白底.png")
    ck("图片探测：中文路径能读", r1["decode_ok"] == 1 and not r1["error"], r1["error"])
    ck("图片探测：尺寸正确", (r1["width"], r1["height"]) == (900, 1200),
       f"{r1['width']}x{r1['height']}")
    ck("图片探测：duration_ms = 0（静帧，不编造时长）", r1["duration_ms"] == 0,
       r1["duration_ms"])
    ck("图片探测：kind = image", r1["kind"] == "image", r1["kind"])

    r2 = img.probe_image(tmp / "大写扩展.PNG")
    ck("大写扩展名 .PNG 也能识别", r2["decode_ok"] == 1 and r2["width"] == 300,
       f"{r2['decode_ok']}/{r2['width']}")

    ck("is_image 对 .JPG 大小写都成立",
       img.is_image("a.JPG") and img.is_image("b.jpg"))
    ck("is_supported 认视频也认图片",
       img.is_supported("a.mov") and img.is_supported("a.png"))
    ck("is_supported 拒绝 txt", not img.is_supported("a.txt"))

    t = img.make_image_thumb(tmp / "测试图_白底.png")
    ck("中文路径能生成缩略图", bool(t) and Path(t).exists(), t)
    if t:
        pm = cv2.imdecode(np.fromfile(t, dtype=np.uint8), cv2.IMREAD_COLOR)
        ck("生成的缩略图可被解码", pm is not None, "None" if pm is None else pm.shape)

    # 损坏图片
    bad_img = tmp / "坏图.png"
    bad_img.write_bytes(b"not an image")
    rb = img.probe_image(bad_img)
    ck("损坏图片如实报错、不崩", rb["decode_ok"] == 0 and bool(rb["error"]), rb["error"])

    # 不存在的文件
    rn = img.probe_image(tmp / "不存在.png")
    ck("不存在的图片报'文件不存在'", "不存在" in rn["error"], rn["error"])

    # probe_any 分派
    ck("probe_any 对图片走图片分支",
       img.probe_any(tmp / "测试图_白底.png")["kind"] == "image")

    # ================= 6. 空项目 =================
    empty_path = tmp / "empty.db"
    edb = ProjectDB(empty_path)
    epv = bridge.load_project(edb, empty_path)
    ck("空项目素材数 = 0", len(epv.assets) == 0, len(epv.assets))
    ck("空项目统计 total = 0", epv.stats.total == 0, epv.stats.total)
    ck("空项目进度 = 0%，不除零崩溃", epv.stats.progress_pct == 0)
    ck("空项目仍有'全部'分组", len(epv.groups) == 1 and epv.groups[0].count == 0,
       len(epv.groups))

    # ================= 7. 只读性验证 =================
    # 记录读之前的库文件哈希，读完再比
    import hashlib

    def fhash(p):
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()

    h_before = fhash(db_path)
    for _ in range(3):
        bridge.load_project(db, db_path)
        bridge.load_segments(db)
        bridge.ai_capability_summary(db)
    h_after = fhash(db_path)
    ck("load_project / load_segments 不写库（文件哈希不变）",
       h_before == h_after, f"{h_before[:12]} vs {h_after[:12]}")

    # ================= 8. 镜头视图 =================
    segs = bridge.load_segments(db)
    ck("空时间线 → 镜头列表为空（不报错）", isinstance(segs, list) and len(segs) == 0,
       len(segs))

    # ================= 9. AI 能力摘要必须如实 =================
    cap = bridge.ai_capability_summary(db)
    ck("能力摘要：has_vlm = False（没接模型就不能说接了）", cap["has_vlm"] is False)
    ck("能力摘要：has_cloud = False", cap["has_cloud"] is False)
    ck("能力摘要：说明含'未接入'字样", "未接入" in cap["note"], cap["note"])

    # ================= 10. 真实库回归（用演示库） =================
    demo = ROOT / "projects" / "_stage9_full.db"
    if demo.exists():
        ddb = ProjectDB(demo)
        dpv = bridge.load_project(ddb, demo)
        ck("真实演示库可读取", len(dpv.assets) > 0, len(dpv.assets))
        ck("真实演示库有分组", len(dpv.groups) > 1, len(dpv.groups))
        ck("真实演示库素材状态都在五态内",
           all(a.status in (M.ST_UNANALYZED, M.ST_ANALYZING, M.ST_MEASURED,
                            M.ST_CONFIRM, M.ST_FAILED) for a in dpv.assets))
    else:
        ck("真实演示库可读取", False, "演示库不存在，跳过")

    shutil.rmtree(tmp, ignore_errors=True)

    # ================= 汇总 =================
    passed = sum(1 for c in checks if c["ok"])
    out = {
        "stage": "B",
        "suite": "workshop_data",
        "total": len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
    }
    res_dir = ROOT / "tests"
    res_dir.mkdir(exist_ok=True)
    (res_dir / "test_result_workshop_data.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"WORKSHOP_DATA {passed}/{len(checks)}")
    for c in checks:
        if not c["ok"]:
            print(f"  FAIL {c['name']}  {c['detail']}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
