# -*- coding: utf-8 -*-
"""人工评分校准自动质量分 — 单元测试（不依赖真实视频文件）。

覆盖：
- 样本不足时不假装已校准
- ≥3 条人工分后仿射校准生效
- ≥6 条可升到六维权重模式
- apply 后 total 贴近人分、保留 raw_total
- ProjectDB 持久化 human_rating + calibration
- storyboard_matcher 优先使用人工分
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db as dbmod
from app.core import score_calibrator, quality_scorer, storyboard_matcher

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append({"name": name, "pass": bool(cond), "detail": detail})
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f" — {detail}" if detail else ""))


def _fake_scores(base, jitter=0):
    """造一组六维分。"""
    dims = quality_scorer.DIMENSIONS
    return {d: max(0, min(100, base + (i - 2) * jitter)) for i, d in enumerate(dims)}


def _clip_row(i, scores, human, auto_total=None):
    if auto_total is None:
        auto_total = round(sum(scores[d] * quality_scorer.DEFAULT_WEIGHTS[d]
                               for d in quality_scorer.DIMENSIONS))
    return {
        "id": i,
        "human_rating": human,
        "quality_raw_total": auto_total,
        "quality_total": auto_total,
        "quality_detail": json.dumps({"scores": scores, "grade": "可用"}, ensure_ascii=False),
        "score_text": json.dumps({"ok": True, "scores": scores, "total": auto_total,
                                  "raw_total": auto_total}, ensure_ascii=False),
    }


print("=" * 70)
print("人工评分校准测试")
print("=" * 70)

# ---------- 1. 样本不足 ----------
print("\n[1] 样本不足不校准")
ex0 = [_clip_row(1, _fake_scores(70), 80)]
model0 = score_calibrator.fit_calibration(score_calibrator.collect_labeled_examples(ex0))
check("1 条样本 ok=False", model0.get("ok") is False, model0.get("message", ""))
check("mode=none", model0.get("mode") == "none")

# ---------- 2. 仿射校准 ----------
print("\n[2] ≥3 条仿射校准")
# 人工始终比自动高约 10 分 → 期望 b≈10, a≈1
rows = [
    _clip_row(1, _fake_scores(60), 70, 60),
    _clip_row(2, _fake_scores(70), 80, 70),
    _clip_row(3, _fake_scores(80), 90, 80),
]
ex = score_calibrator.collect_labeled_examples(rows)
model = score_calibrator.fit_calibration(ex)
check("3 条样本 ok=True", model.get("ok") is True, str(model))
check("mode=affine", model.get("mode") == "affine", model.get("mode"))
check("斜率接近 1", abs(model.get("a", 0) - 1.0) < 0.2, f"a={model.get('a')}")
check("截距接近 10", abs(model.get("b", 0) - 10.0) < 3.0, f"b={model.get('b')}")

raw = {
    "ok": True, "scores": _fake_scores(65), "total": 65, "raw_total": 65,
    "grade": "需要人工检查", "detail": {}, "disclaimer": "x",
}
cal = score_calibrator.apply_calibration(dict(raw), model)
check("校准后 total 升高", cal["total"] > 65, f"total={cal['total']}")
check("保留 raw_total", cal.get("raw_total") == 65, str(cal.get("raw_total")))
check("calibrated=True", cal.get("calibrated") is True)
check("disclaimer 提到校准", "校准" in (cal.get("disclaimer") or ""))

# ---------- 3. 六维权重模式 ----------
print("\n[3] ≥6 条可进入 weighted")
rows6 = []
for i in range(8):
    base = 50 + i * 5
    # 人造偏好：更看清晰度 — 用清晰度主导人工分
    sc = _fake_scores(base, jitter=3)
    sc["sharpness"] = min(100, base + 20)
    human = int(0.6 * sc["sharpness"] + 0.4 * base)
    rows6.append(_clip_row(i + 1, sc, human, base))
model6 = score_calibrator.fit_calibration(score_calibrator.collect_labeled_examples(rows6))
check("8 条样本 ok", model6.get("ok") is True)
check("mode 为 affine 或 weighted", model6.get("mode") in ("affine", "weighted"),
      model6.get("mode"))

# ---------- 4. quality_scorer 接入 calibration 参数（无视频时测 apply 路径） ----------
print("\n[4] apply_calibration 空模型不改分")
unchanged = score_calibrator.apply_calibration(dict(raw), None)
check("无模型不改 total", unchanged["total"] == 65)
check("无模型 calibrated=False", unchanged.get("calibrated") is False)

# ---------- 5. ProjectDB 持久化 ----------
print("\n[5] ProjectDB 人工评分 + 校准持久化")
tmpdir = tempfile.mkdtemp(prefix="mmc_hr_")
db_path = Path(tmpdir) / "human_rating.db"
db = dbmod.ProjectDB(str(db_path))
db.set_project_name("人工评分测试")
# 造素材与片段
aid = db.add_asset({
    "path": str(Path(tmpdir) / "dummy.mp4"), "filename": "dummy.mp4",
    "folder": tmpdir, "size_bytes": 1, "duration_ms": 5000,
    "width": 100, "height": 100, "fps": 25, "rotation": 0,
    "codec": "h264", "has_audio": 0, "decode_ok": 1,
    "thumb_path": "", "error": "",
})
cids = []
for i, (auto, human) in enumerate([(60, 72), (70, 82), (80, 92)]):
    sc = _fake_scores(auto)
    cid = db.add_clip({
        "storyboard_id": None, "asset_id": aid, "start_ms": i * 1000,
        "end_ms": i * 1000 + 900, "primary_tag": "", "confidence": 0.5,
        "score_text": "", "recommend_reason": "", "potential_issue": "",
        "verify_state": "待核验", "source": "auto_scene",
        "keyframe_paths": "[]", "cut_reason": "", "shot_index": i,
        "analysis_status": "待核验",
    })
    cids.append(cid)
    # 先写入自动分
    db.save_semantic(cid, {"ok": True, "labels": [], "metrics": {}, "review_reasons": []},
                     {"ok": True, "scores": sc, "total": auto, "raw_total": auto,
                      "grade": "可用", "detail": {d: "" for d in quality_scorer.DIMENSIONS}})
    ok, msg, m = db.save_human_rating(cid, human, note=f"label-{i}")
    check(f"保存人工分#{i+1}", ok, msg)

model_db = db.get_score_calibration()
check("DB 中校准 ok", bool(model_db and model_db.get("ok")), str(model_db))
check("settings 可重读", db.get_score_calibration().get("n_samples") == 3)

# 重开项目仍在
db2 = dbmod.ProjectDB(str(db_path))
c0 = next(c for c in db2.get_clips() if c["id"] == cids[0])
check("重开后 human_rating 仍在", c0.get("human_rating") == 72, str(c0.get("human_rating")))
check("重开后校准仍在", bool(db2.get_score_calibration() and db2.get_score_calibration().get("ok")))

# 校准后 quality_total 应被刷新（接近 human）
c1 = next(c for c in db2.get_clips() if c["id"] == cids[1])
check("校准后质量分靠近人工分", abs(int(c1.get("quality_total") or 0) - 82) <= 8,
      f"quality_total={c1.get('quality_total')} human=82 raw={c1.get('quality_raw_total')}")

# ---------- 6. matcher 优先人工分 ----------
print("\n[6] matcher 用人分作质量")
clip_h = {"human_rating": 95, "quality_total": 40, "score_text": ""}
clip_a = {"human_rating": None, "quality_total": 88, "score_text": "总分88(良好)｜"}
check("有人工分时用 95", storyboard_matcher._parse_quality(clip_h) == 95)
check("无人工分时用 quality_total", storyboard_matcher._parse_quality(clip_a) == 88)

# ---------- 汇总 ----------
passed = sum(1 for r in RESULTS if r["pass"])
failed = sum(1 for r in RESULTS if not r["pass"])
print("\n" + "=" * 70)
print(f"结果：通过 {passed} / 失败 {failed} / 合计 {len(RESULTS)}")
print("=" * 70)
out = Path(__file__).with_name("test_human_rating_result.json")
out.write_text(json.dumps({"passed": passed, "failed": failed, "results": RESULTS},
                          ensure_ascii=False, indent=2), encoding="utf-8")
sys.exit(0 if failed == 0 else 1)
