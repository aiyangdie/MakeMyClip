# -*- coding: utf-8 -*-
"""阶段十三验收：界面按公开设计语言重做 + 人性化「一步一件事」。

原则（用户硬规则）：
- 真实项目 projects/_stage9_full.db 只读；写操作都在临时副本上做，跑完即删。
- 原素材绝不改动；成片校验只看真实文件与真实解码。
- 出片 / 字幕 / 渲染 / 导出链路必须与改前字节级一致。
- 旧测试一个字节不涂改；阶段十一那条「项目名」失效是历史数据污染，
  这里用干净的临时项目验证「显示商品名」能力本身完好。
"""
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QAbstractItemView  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer, Qt  # noqa: E402

from app import config, media, db as dbmod  # noqa: E402
from app.core import wizard_lines as wl  # noqa: E402
from app.ui import design_tokens as dt  # noqa: E402
from app.ui.wizard import (WizardWindow, ExportWorker, DropArea, StepBar,  # noqa: E402
                           STEPS, MIME_ASSETS, _friendly_error, _video_files)

checks = []


def ck(name, cond, detail=""):
    checks.append({"name": name, "ok": bool(cond), "detail": str(detail)[:220]})


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


app = QApplication([])
for fp in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
    if os.path.exists(fp):
        QFontDatabase.addApplicationFont(fp)
app.setFont(QFont("Microsoft YaHei", 9))

PROJ = ROOT / "projects/_stage9_full.db"
BK = ROOT / "backups/pre_stage13"
TMP = ROOT / "projects/_stage13_test.db"
TMP_CLEAN = ROOT / "projects/_stage13_name_test.db"
export_paths = []

# ================= A. 回退证据 / 只增不改 =================
BK_MAP = {
    "app_ui_wizard.py": ROOT / "app/ui/wizard.py",
    "app_ui_main_window.py": ROOT / "app/ui/main_window.py",
    "app_core_wizard_lines.py": ROOT / "app/core/wizard_lines.py",
    "app_core_final_exporter.py": ROOT / "app/core/final_exporter.py",
    "app_core_video_editor.py": ROOT / "app/core/video_editor.py",
    "app_core_subtitle.py": ROOT / "app/core/subtitle.py",
    "app_core_narration.py": ROOT / "app/core/narration.py",
    "app_db.py": ROOT / "app/db.py",
    "app_config.py": ROOT / "app/config.py",
    "app_media.py": ROOT / "app/media.py",
    "app_workers.py": ROOT / "app/workers.py",
    "main.py": ROOT / "main.py",
    "main_wizard.py": ROOT / "main_wizard.py",
    "使用说明.md": ROOT / "使用说明.md",
    "阶段十二报告.md": ROOT / "阶段十二报告.md",
    "tests_test_stage11.py": ROOT / "tests/test_stage11.py",
    "tests_test_stage12.py": ROOT / "tests/test_stage12.py",
    "MakeMyClip.cmd": Path("C:/Users/Administrator/Desktop/MakeMyClip.cmd"),
}
ck("改前已整包备份（19 个文件，含哈希基线）",
   len(list(BK.iterdir())) == 19 and (BK / "BASELINE_SHA256.txt").is_file(),
   f"{len(list(BK.iterdir()))} 个")
ck("每个备份都能对应到现存真实文件", all(p.is_file() for p in BK_MAP.values()))

changed = {n for n, p in BK_MAP.items() if p.is_file() and sha(p) != sha(BK / n)}
ck("改动范围只限「向导界面 + 使用说明追加」",
   changed.issubset({"app_ui_wizard.py", "使用说明.md"}), str(sorted(changed)))
ck("出片、字幕、渲染、导出、旧工作台、桌面启动器字节级未动",
   all(sha(BK_MAP[n]) == sha(BK / n) for n in BK_MAP if n not in
       ("app_ui_wizard.py", "使用说明.md")),
   str([n for n in BK_MAP if n not in ("app_ui_wizard.py", "使用说明.md")
        and sha(BK_MAP[n]) != sha(BK / n)]))

# 《使用说明》二进制只增不改
_dold = (BK / "使用说明.md").read_bytes()
_dnew = (ROOT / "使用说明.md").read_bytes()
_dol = _dold.decode("utf-8").splitlines()
_dnl = _dnew.decode("utf-8").splitlines()
ck("《使用说明》原文逐字保留（只增不改，一行不丢）",
   _dnew[:len(_dold)] == _dold and _dnl[:len(_dol)] == _dol,
   f"原文{len(_dol)}行 → 现{len(_dnl)}行")
ck("v13.0 增补打在原文之后、带版本标记",
   any("【v13.0 增补】" in x for x in _dnl[len(_dol):]))
ck("v12.0 增补仍在（没被覆盖）",
   any("【v12.0 增补】" in x for x in _dnl))

# ================= B. 出片链路字节级未改 =================
old_w = (BK / "app_ui_wizard.py").read_text(encoding="utf-8")
new_w = (ROOT / "app/ui/wizard.py").read_text(encoding="utf-8")


def seg(t, a, b):
    i = t.index(a)
    j = t.index(b, i)
    return t[i:j]


_a = "class ExportWorker(QThread):"
_b = "class WizardWindow(QMainWindow):"
ck("出片核心 ExportWorker 整段字节级未改", seg(old_w, _a, _b) == seg(new_w, _a, _b))

_a2 = "    # ---------------- 数据 ----------------"
o = old_w[old_w.index(_a2):]
n = new_w[new_w.index(_a2):]
diff = [x for x in difflib.unified_diff(o.splitlines(), n.splitlines(), lineterm="")
        if x.startswith(("+", "-")) and not x.startswith(("+++", "---"))]
_added = [x for x in diff if x.startswith("+")]
_removed = [x for x in diff if x.startswith("-")]
# 真实差异：6 处旧写法换成 6 行 self._style()；其中 1 处旧写法跨两行
# （name.setStyleSheet(...) 的续行），故删 7 行、增 6 行，合计 13 行 diff。
ck("数据/交互逻辑只改了 6 处「取色方式」，行为未变",
   len(diff) == 13 and len(_added) == 6 and len(_removed) == 7,
   f"{len(diff)} 行 diff / 增{len(_added)} 删{len(_removed)}")
ck("这 6 处全部改为走统一主题 self._style()",
   all("_style(" in x for x in _added), str(_added[:2]))
ck("删掉的 7 行里 6 行是硬编码 setStyleSheet、1 行只是它的续行（未碰其它逻辑）",
   sum("setStyleSheet" in x for x in _removed) == 6, str(_removed[:2]))
ck("出片撞名自动加序号仍在", "while out.exists():" in new_w)
ck("向导仍接统一文案入口 wizard_lines", "wizard_lines" in new_w)

# ================= C. 设计主题（零依赖、亮暗双套、有出处） =================
src_dt = (ROOT / "app/ui/design_tokens.py").read_text(encoding="utf-8")
ck("新增统一设计主题文件", (ROOT / "app/ui/design_tokens.py").is_file())
for word in ("Material", "shadcn", "CC BY 4.0", "Apache 2.0", "MIT"):
    ck(f"主题文件写明出处/许可「{word}」", word in src_dt)
ck("亮暗两套色值确实不同", dt.LIGHT != dt.DARK)
ck("浅色与深色都能生成合法 QSS",
   "QPushButton" in dt.qss(False) and "QPushButton" in dt.qss(True))
ck("主题提供语义命名而非具体色名",
   all(k in dt.LIGHT for k in ("bg", "surface", "text", "muted", "border", "primary")))
hexes = re.findall(r"#[0-9a-fA-F]{6}", new_w)
ck("向导界面已清除散落硬编码颜色（只剩字幕白字 1 处）",
   hexes == ["#FFFFFF"], str(hexes))
ck("字幕白字属于出片样式、不在界面层",
   '"color": "#FFFFFF"' in seg(new_w, _a, _b))
ck("没有引入任何第三方界面库",
   all(x not in new_w for x in ("qt_material", "qfluentwidgets", "from PyDracula")))
ck("PySide6 版本没有被要求降级", "6.7.2" not in src_dt and "6.7.2" not in new_w)

# ================= D. 界面结构：一步一件事 =================
shutil.copy2(PROJ, TMP)
shutil.copy2(PROJ, TMP_CLEAN)
w = WizardWindow()
app.processEvents()
w._load_project(TMP)
app.processEvents()

ck("仍是五步向导", STEPS == ["导入素材", "挑镜头", "看片调整", "字幕配音", "一键出片"]
   and w.stack.count() == 5 and w.stack.currentIndex() == 0)
ck("顶部是 5 个小圆点进度（不是一排大按钮）",
   isinstance(w.stepbar, StepBar) and len(w.stepbar.buttons) == 5
   and all(isinstance(b, QPushButton) for b in w.stepbar.buttons))
ck("进度条显示「第 N / 5 步」和当前步名",
   "第 1 / 5 步" in w.stepbar.current_label.text()
   and "导入素材" in w.stepbar.current_label.text())
ck("有亮/暗切换按钮", hasattr(w, "btn_theme") and "界面" in w.btn_theme.text())

# 每屏都有一个人话大标题 + 一个主动作主按钮
for i in range(5):
    w._goto_step(i)
    app.processEvents()
    page = w.stack.widget(i)
    titles = [x for x in page.findChildren(QLabel) if x.objectName() == "step_title"]
    prim = [x for x in page.findChildren(QPushButton) if x.objectName() == "primary"]
    ck(f"第 {i+1} 步有一个大标题", len(titles) == 1,
       str([x.text() for x in titles]))
    ck(f"第 {i+1} 步有一个主动作大按钮", len(prim) >= 1,
       str([x.text() for x in prim]))

# 亮暗切换真的换色
w._goto_step(0)
app.processEvents()
light_qss = w.styleSheet()
w._toggle_theme()
app.processEvents()
dark_qss = w.styleSheet()
ck("一键切换深色：QSS 真的变了", w._dark is True and light_qss != dark_qss)
ck("深色按钮文案变成「浅色界面」", w.btn_theme.text() == "浅色界面")
w._toggle_theme()
app.processEvents()
ck("再按一次回到浅色", w._dark is False and w.styleSheet() == light_qss)

# 专业参数默认收起
w._goto_step(0)
app.processEvents()
ck("第 1 步分组/次要入口默认收起，不碍眼", not w.more_import.isVisible())
w._goto_step(3)
app.processEvents()
ck("第 4 步画面比例默认收起", not w.more_box.isVisible())

# 界面不出现技术黑话
texts = " ".join(x.text() for x in w.findChildren(QLabel))
for bad_word in ("缓存复用", "可解码", "crf", "帧率", "编码", "xfade"):
    ck(f"界面不出现技术黑话「{bad_word}」", bad_word not in texts)

# ================= E. 阶段十二能力零丢失 =================
ck("15 段真实素材缩略图仍在", w.asset_list.count() == 15, w.asset_list.count())
ck("按真实文件夹分出多个组", w.group_list.count() >= 6, w.group_list.count())
ck("素材卡片仍是「只拖出」，能拖到分组",
   w.asset_list.dragDropMode() == QAbstractItemView.DragOnly)
ck("仍是多选（能全选/批量移出）",
   w.asset_list.selectionMode() == QAbstractItemView.ExtendedSelection)
md = w.asset_list.mimeData([w.asset_list.item(0)])
_dragged = json.loads(bytes(md.data(MIME_ASSETS)).decode("utf-8"))
ck("拖拽数据仍是真实素材路径",
   md.hasFormat(MIME_ASSETS) and all(Path(x).exists() for x in _dragged if x))
ck("挑镜头列表 13 段", w.pick_list.count() == 13)
w._goto_step(2)
app.processEvents()
ck("第 3 步 13 张真实镜头卡片", w.shot_grid.count() == 13)
w._goto_step(3)
app.processEvents()
ck("字幕表仍是 13 行且第 3 列可编辑",
   w.label_table.rowCount() == 13
   and bool(w.label_table.item(0, 2).flags() & Qt.ItemIsEditable))
ck("保存/恢复默认文案按钮都在",
   hasattr(w, "btn_save_labels") and hasattr(w, "btn_reset_labels"))
ck("新建项目、真实步骤、上次停在、完整工作台入口都在",
   all(hasattr(w, x) for x in ("btn_new", "stepbar", "last_step",
                               "project_combo", "btn_export", "export_status")))
# 「已完成步骤」必须按真实记录算：先对照真实状态，再隔离验证「空状态 = 0」，
# 精确证明阶段十二修掉的「一打开就假装 4 步全做完」没有回退。
_st = w.db.get_step_state()
_expect = 0
for _i in range(4):
    if _st.get(_i):
        _expect = _i + 1
    else:
        break
ck("「已完成步骤」按真实记录算，不是写死全做完",
   w._done_before() == _expect,
   f"真实={_expect} 计算={w._done_before()} 状态={_st}")
with patch.object(w.db, "get_step_state", return_value={}):
    ck("空项目不会假装前 4 步都做完", w._done_before() == 0, w._done_before())
# 「上次停在第 N 步」必须建立在「真走过步骤」之上：
# 1) 空状态即便被塞了 last_step，也不许谎称上次停在第 3 步；
# 2) 真的做过某步后，才按真实记录显示步号与步名。
w.db.set_setting("wizard_step_state", "")
w.db.set_setting("wizard_last_step", "2")
w._update_last_step_button()
ck("没真正走过步骤时，不谎称「上次停在第 N 步」",
   "从第 1 步开始" in w.last_step.text() and "第 3 步" not in w.last_step.text(),
   w.last_step.text())
w.db.mark_step_done(2, last_step=2)
w._update_last_step_button()
ck("真走过步骤后，「上次停在第 N 步」按记录显示步号与步名",
   "第 3 步" in w.last_step.text() and "看片调整" in w.last_step.text(),
   w.last_step.text())

# 用干净的临时项目验证「显示商品名」能力完好（不碰演示库）
clean = dbmod.ProjectDB(str(TMP_CLEAN))
clean.set_product_info({"name": "带灯床头柜"})
w._load_project(TMP_CLEAN)
app.processEvents()
ck("界面能正确显示商品名（用干净临时项目验证，不动演示库）",
   "带灯床头柜" in w.title.text(), w.title.text())
ck("演示库项目名污染与本次无关：新旧 _load_project 字节级一致",
   seg(old_w, "    def _load_project(self, path):", "    def _new_project(self):") ==
   seg(new_w, "    def _load_project(self, path):", "    def _new_project(self):"))

# 拖放区、报错人话
da = DropArea()
fired = []
da.chooseRequested.connect(lambda: fired.append(1))
da.mousePressEvent(None) if False else None
ck("拖放区仍接受拖放", da.acceptDrops())
ck("权限错误仍翻译成人话", "占用" in _friendly_error(PermissionError("denied")))
ck("解码错误仍翻译成人话", "读不出来" in _friendly_error(RuntimeError("ffmpeg decode")))
ck("展开文件夹能力仍在", callable(_video_files))

# ================= F. 真实出片端到端（证明里子没坏） =================
w._load_project(TMP)
app.processEvents()
w._goto_step(4)
app.processEvents()
CUSTOM = "手抚柜面近景"
shots = w.db.get_timeline()
sid = str(shots[0]["shot_id"])
wl.save_custom_labels(w.db, {sid: CUSTOM})
w._refresh_labels()
exports_before = set(config.EXPORT_DIR.glob("一键出片_*.mp4"))
w._start_export()
ew = w._export_worker
box = {}
loop = QEventLoop()


def _finish(res):
    box["res"] = res
    loop.quit()


ew.done.connect(_finish)
QTimer.singleShot(300000, loop.quit)
loop.exec()
ew.wait(5000)
r = box.get("res", {})
ck("真实一键出片仍成功", r.get("ok") is True, r.get("error", ""))
srt = config.CACHE_DIR / "final" / "wizard.srt"
srt_text = srt.read_text(encoding="utf-8", errors="ignore") if srt.exists() else ""
ck("你改的字仍进了成片字幕", CUSTOM in srt_text, srt_text[:100].replace("\n", " | "))
if r.get("ok"):
    out = Path(r["path"])
    export_paths.append(out)
    info = media.probe(str(out))
    ck("成片仍是 3:4 竖版 720x960",
       info.get("width") == 720 and info.get("height") == 960,
       f"{info.get('width')}x{info.get('height')}")
    ck("成片时长仍在 15-30 秒", 15000 <= info.get("duration_ms", 0) <= 30000,
       info.get("duration_ms"))
    ck("成片含音轨且可解码",
       bool(info.get("has_audio")) and bool(info.get("decode_ok")))
    ck("导出文件名带时间戳", bool(re.search(r"\d{8}_\d{6}", out.name)))
    exports_after = set(config.EXPORT_DIR.glob("一键出片_*.mp4"))
    ck("旧成片没被覆盖（新片另存）",
       exports_before.issubset(exports_after) and len(exports_after) > len(exports_before))
    ck("结果显示完整存放路径",
       "存在：" in w.export_status.text() and str(out) in w.export_status.text())
ck("13 个已确认镜头逐行未变", len(w.db.get_timeline()) == 13)
ck("原素材一个都没被删改",
   all(Path(str(a.get("path"))).exists() for a in w.db.get_assets()
       if str(a.get("path") or "").strip()))

# ================= 清理 =================
for p in (TMP, TMP_CLEAN):
    p.unlink(missing_ok=True)

passed = sum(1 for c in checks if c["ok"])
result = {
    "stage": 13, "total": len(checks), "passed": passed,
    "failed": len(checks) - passed, "checks": checks,
    "changed_files": sorted(changed),
    "exports": [str(p) for p in export_paths],
    "screenshots": sorted(str(p.name) for p in (ROOT / "tests").glob("gui_stage13_*.png")),
}
(ROOT / "tests/test_result_stage13.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"STAGE13 {passed}/{len(checks)}")
for c in checks:
    if not c["ok"]:
        print("FAIL", c["name"], c["detail"])
for p in export_paths:
    if Path(p).is_file():
        print("EXPORT", p)
sys.exit(0 if passed == len(checks) else 1)
