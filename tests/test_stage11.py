# -*- coding: utf-8 -*-
"""阶段十一验收：向导界面 + 只增不改 + 一键出片真实导出。"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QAbstractItemView  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402

from app import config, media, db as dbmod  # noqa: E402
from app.ui.wizard import WizardWindow, _video_files, STEPS  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

checks = []


def ck(name, cond, detail=""):
    checks.append({"name": name, "ok": bool(cond), "detail": str(detail)[:200]})


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def snap(path):
    d = dbmod.ProjectDB(str(path))
    return [(s["shot_id"], s.get("name"), s.get("asset_path"),
             s.get("start_ms"), s.get("end_ms"), s.get("target_ms"),
             bool(s.get("locked"))) for s in d.get_timeline()]


app = QApplication([])
for fp in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
    if os.path.exists(fp):
        QFontDatabase.addApplicationFont(fp)
app.setFont(QFont("Microsoft YaHei", 9))

# ---- 1. 只增不改（字节级） ----
ck("旧界面文件字节级未改",
   sha(ROOT / "app/ui/main_window.py") == sha(ROOT / "backups/pre_stage11/main_window.py"))
ck("旧入口 main.py 字节级未改",
   sha(ROOT / "main.py") == sha(ROOT / "backups/pre_stage11/main.py"))
ck("新增 wizard.py 存在", (ROOT / "app/ui/wizard.py").is_file())
ck("新增 main_wizard.py 存在", (ROOT / "main_wizard.py").is_file())

# ---- 2. 界面结构 ----
w = WizardWindow()
app.processEvents()
ck("五步流程条", STEPS == ["导入素材", "挑镜头", "看片调整", "字幕配音", "一键出片"])
ck("步骤页数量为5", w.stack.count() == 5)
ck("默认打开第1步（导入素材）", w.stack.currentIndex() == 0)
ck("项目名显示商品名而非文件名", "带灯床头柜" in w.title.text(), w.title.text())
ck("素材画面卡片数量>0", w.asset_list.count() > 0, w.asset_list.count())
ck("镜头列表13行", w.pick_list.count() == 13, w.pick_list.count())
ck("前4步标记已完成", w._done_before() == 4)

# ---- 3. 拖拽上传（真实素材） ----
real_dirs = [p for p in [Path.home() / "Desktop" / "T26单抽视频"]
             if p.exists()]
if real_dirs:
    found = _video_files([str(real_dirs[0])])
    ck("拖入文件夹能识别真实视频", len(found) > 0, f"{len(found)} 条")
else:
    found = _video_files([str(ROOT / "exports")])
    ck("拖放展开逻辑可用（用exports目录自测）", isinstance(found, list))
ck("拖放区接受拖放", w.drop.acceptDrops())

# ---- 4. 术语与截图 ----
texts = " ".join(x.text() for x in w.findChildren(QLabel))
for bad in ("缓存复用", "可解码", "crf", "帧率", "编码"):
    ck(f"界面不出现技术词「{bad}」", bad not in texts)
w.resize(1120, 760)
app.processEvents()
w.grab().save(str(ROOT / "tests/gui_stage11_step1.png"))
w._goto_step(2)
app.processEvents()
ck("镜头缩略图卡片13张", w.shot_grid.count() == 13, w.shot_grid.count())
thumbs = list((config.CACHE_DIR / "wizard_thumbs").glob("*.jpg"))
ck("镜头缩略图是真实抽帧文件（同素材同起点复用）",
   len(thumbs) >= 12, f"{len(thumbs)} 张唯一画面覆盖 13 张卡片")
pics = []
for i in range(w.shot_grid.count()):
    item = w.shot_grid.itemAt(i)
    card = item.widget() if item else None
    if card:
        labs = card.findChildren(QLabel)
        if labs:
            pics.append(labs[0])
with_pic = sum(1 for p in pics if p.pixmap() is not None and not p.pixmap().isNull())
ck("13张镜头卡片都显示真实画面", with_pic == 13, f"{with_pic}/13")
w.grab().save(str(ROOT / "tests/gui_stage11_step3.png"))
w._goto_step(4)
app.processEvents()
w.grab().save(str(ROOT / "tests/gui_stage11_wizard.png"))

# ---- 5. 旧工作台原样可开 ----
mw = MainWindow()
app.processEvents()
ck("旧工作台仍为8个页面", mw.stack.count() == 8, mw.stack.count())

# ---- 6. 一键出片真实导出 ----
proj = ROOT / "projects/_stage9_full.db"
before = snap(proj)
w._goto_step(4)
app.processEvents()
w._start_export()
worker = w._export_worker
box = {}
loop = QEventLoop()


def _finish(res):
    box["res"] = res
    loop.quit()


worker.done.connect(_finish)
QTimer.singleShot(300000, loop.quit)
loop.exec()
r = box.get("res", {})
ck("一键出片执行成功", r.get("ok") is True, r.get("error", ""))
if r.get("ok"):
    out = Path(r["path"])
    ck("成片文件真实存在", out.is_file() and out.stat().st_size > 100000, out.stat().st_size)
    info = media.probe(str(out))
    ck("成片为3:4竖版720x960",
       info.get("width") == 720 and info.get("height") == 960,
       f"{info.get('width')}x{info.get('height')}")
    ck("成片时长落在15-30秒",
       15000 <= info.get("duration_ms", 0) <= 30000,
       info.get("duration_ms"))
    ck("成片含音轨", bool(info.get("has_audio")))
    ck("成片可解码", bool(info.get("decode_ok")))
after = snap(proj)
ck("13个已确认镜头逐行未变", before == after, f"{len(before)} 行")
ck("一键出片未减少镜头数", len(after) == 13, len(after))

# ---- 7. 移出素材（临时副本，绝不碰真实项目与原文件） ----
tmp = ROOT / "projects/_stage11_remove_test.db"
shutil.copy2(proj, tmp)
try:
    w._load_project(tmp)
    app.processEvents()
    n0 = len(w._asset_rows)
    target = w._asset_rows[0]
    target_path = target.get("path", "")
    ck("测试素材原文件真实存在", bool(target_path) and Path(target_path).exists())
    ck("移出按钮默认不可用", not w.btn_remove.isEnabled())
    w.asset_list.setCurrentRow(0)
    app.processEvents()
    ck("选中卡片后移出按钮可用", w.btn_remove.isEnabled())
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        w._remove_selected_asset()
    app.processEvents()
    n1 = len(w._asset_rows)
    ck("移出后素材少一条", n1 == n0 - 1, f"{n0}->{n1}")
    ck("移出未删除磁盘原文件", bool(target_path) and Path(target_path).exists())
    d2 = dbmod.ProjectDB(str(tmp))
    ck("项目记录里已无该素材",
       not any(a.get("path") == target_path for a in d2.get_assets()))
    ck("移出素材不动13个镜头", len(d2.get_timeline()) == 13)
    ck("状态栏明确说明原文件未动", "原视频没动" in w.status_label.text())
finally:
    tmp.unlink(missing_ok=True)

# ---- 7b. 批量移出：多选 / 全选 / 一次移走多段（临时副本） ----
tmp2 = ROOT / "projects/_stage11_multi_remove_test.db"
shutil.copy2(proj, tmp2)
try:
    w._load_project(tmp2)
    app.processEvents()
    m0 = len(w._asset_rows)
    ck("素材卡片可一次选多段",
       w.asset_list.selectionMode() == QAbstractItemView.ExtendedSelection)
    ck("有全选按钮", hasattr(w, "btn_select_all") and w.btn_select_all.isEnabled())
    # 一次选中 3 段（模拟按住 Ctrl 逐个点）
    w.asset_list.clearSelection()
    for i in range(3):
        w.asset_list.item(i).setSelected(True)
    app.processEvents()
    ck("一次能选中3段", len(w.asset_list.selectedItems()) == 3,
       len(w.asset_list.selectedItems()))
    ck("按钮写明已选段数", "3 段" in w.btn_remove.text(), w.btn_remove.text())
    chosen = w.asset_list.selectedItems()
    paths = [w._asset_rows[w.asset_list.row(it)].get("path", "") for it in chosen]
    ck("待移出原文件都真实存在", all(p and Path(p).exists() for p in paths))
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as mq:
        w._remove_selected_asset()
        confirm_text = " ".join(str(a) for a in mq.call_args.args) if mq.call_args else ""
    ck("确认框写明移出3段", "3 段" in confirm_text, confirm_text[:80])
    app.processEvents()
    ck("一次移走了3段", len(w._asset_rows) == m0 - 3, f"{m0}->{len(w._asset_rows)}")
    ck("批量移出未删除任何磁盘原文件",
       all(p and Path(p).exists() for p in paths))
    d3 = dbmod.ProjectDB(str(tmp2))
    ck("批量移出后项目记录里3条都没了",
       all(not any(a.get("path") == p for a in d3.get_assets()) for p in paths))
    ck("批量移出不动13个镜头", len(d3.get_timeline()) == 13)
    ck("批量移出状态栏写明段数", "3 段" in w.status_label.text(),
       w.status_label.text())
    # 全选 / 取消全选
    w.btn_select_all.click()
    app.processEvents()
    ck("点全选一次选中全部",
       len(w.asset_list.selectedItems()) == w.asset_list.count(),
       f"{len(w.asset_list.selectedItems())}/{w.asset_list.count()}")
    ck("全选后按钮变「取消全选」", w.btn_select_all.text() == "取消全选",
       w.btn_select_all.text())
    w.btn_select_all.click()
    app.processEvents()
    ck("再点一次全部取消选中", len(w.asset_list.selectedItems()) == 0,
       len(w.asset_list.selectedItems()))
finally:
    tmp2.unlink(missing_ok=True)

# ---- 结果 ----
passed = sum(1 for c in checks if c["ok"])
result = {"stage": 11, "total": len(checks), "passed": passed,
          "failed": len(checks) - passed, "checks": checks,
          "export": r if r.get("ok") else {"ok": False, "error": r.get("error", "")}}
(ROOT / "tests/test_result_stage11.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"STAGE11 {passed}/{len(checks)}")
for c in checks:
    if not c["ok"]:
        print("FAIL", c["name"], c["detail"])
if r.get("ok"):
    print("EXPORT", r["path"])
sys.exit(0 if passed == len(checks) else 1)
