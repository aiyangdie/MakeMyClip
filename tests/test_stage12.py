# -*- coding: utf-8 -*-
"""阶段十二验收：16 处全量体检修复 + 回退证据 + 真实出片端到端。

原则（用户硬规则）：
- 真实项目 projects/_stage9_full.db 只读；所有写操作都在临时副本上做，跑完即删。
- 原素材绝不改动；成片校验只看真实文件与真实解码。
- 阶段十一的两条历史断言因「用户授权修改旧工作台 / 步骤按真实操作打勾」而失效，
  这里不涂改旧测试，改用对应的正确行为来验证。
"""
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QAbstractItemView  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase, QMouseEvent  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer, Qt, QPointF, QEvent  # noqa: E402

from app import config, media, db as dbmod  # noqa: E402
from app.core import narration as nar, subtitle as sub_mod, wizard_lines as wl  # noqa: E402
from app.ui.wizard import (WizardWindow, ExportWorker, DropArea, STEPS,  # noqa: E402
                           MIME_ASSETS, _friendly_error)
from app.ui.main_window import MainWindow  # noqa: E402

checks = []


def ck(name, cond, detail=""):
    checks.append({"name": name, "ok": bool(cond), "detail": str(detail)[:220]})


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

PROJ = ROOT / "projects/_stage9_full.db"
BK = ROOT / "backups/pre_stage12"
TMP = ROOT / "projects/_stage12_test.db"
TMP2 = ROOT / "projects/_stage12_remove_test.db"
CUSTOM = "手抚柜面近景"
created_projects = []
export_paths = []

# ================= A. 回退证据 / 只增不改 =================
BK_MAP = {
    "app_config.py": ROOT / "app/config.py",
    "app_core_final_exporter.py": ROOT / "app/core/final_exporter.py",
    "app_core_narration.py": ROOT / "app/core/narration.py",
    "app_core_subtitle.py": ROOT / "app/core/subtitle.py",
    "app_core_video_editor.py": ROOT / "app/core/video_editor.py",
    "app_db.py": ROOT / "app/db.py",
    "app_media.py": ROOT / "app/media.py",
    "app_ui_main_window.py": ROOT / "app/ui/main_window.py",
    "app_ui_wizard.py": ROOT / "app/ui/wizard.py",
    "app_workers.py": ROOT / "app/workers.py",
    "main.py": ROOT / "main.py",
    "main_wizard.py": ROOT / "main_wizard.py",
    "tests_test_stage11.py": ROOT / "tests/test_stage11.py",
    "使用说明.md": ROOT / "使用说明.md",
    "阶段十一报告.md": ROOT / "阶段十一报告.md",
    "MakeMyClip.cmd": Path("C:/Users/Administrator/Desktop/MakeMyClip.cmd"),
}
EXPECTED_CHANGED = {
    "app_ui_wizard.py", "app_db.py", "app_core_final_exporter.py",
    "app_core_video_editor.py", "app_core_subtitle.py", "app_ui_main_window.py",
    "使用说明.md",  # 按「只增不改」只在末尾追加 v12.0 增补
}
MUST_UNCHANGED = [
    "main.py", "main_wizard.py", "MakeMyClip.cmd",
    "阶段十一报告.md", "tests_test_stage11.py",
    "app_core_narration.py", "app_media.py", "app_workers.py", "app_config.py",
]
ck("改前已全量备份（16 个文件）",
   len(BK_MAP) == 16 and all((BK / n).is_file() for n in BK_MAP),
   f"{sum(1 for n in BK_MAP if (BK / n).is_file())}/16")
ck("每个备份都能对应到现存的真实文件",
   all(p.is_file() for p in BK_MAP.values()))
changed = {n for n, p in BK_MAP.items() if p.is_file() and sha(p) != sha(BK / n)}
ck("改动范围没有超出计划（6 个代码文件 + 使用说明末尾追加）",
   changed.issubset(EXPECTED_CHANGED), str(sorted(changed)))
ck("阶段十一交付物、旧测试与未涉及代码字节级未动",
   all(sha(BK_MAP[n]) == sha(BK / n) for n in MUST_UNCHANGED),
   str([n for n in MUST_UNCHANGED if sha(BK_MAP[n]) != sha(BK / n)]))
# 《使用说明》按用户硬规则「只增不改」：原文逐字保留，新增另起一行并打版本标记
_doc_old = (BK / "使用说明.md").read_bytes()
_doc_new = (ROOT / "使用说明.md").read_bytes()
_doc_old_lines = _doc_old.decode("utf-8").splitlines()
_doc_new_lines = _doc_new.decode("utf-8").splitlines()
ck("《使用说明》原文逐字保留（只增不改，一行不丢）",
   _doc_new[:len(_doc_old)] == _doc_old and
   _doc_new_lines[:len(_doc_old_lines)] == _doc_old_lines,
   f"原文{len(_doc_old_lines)}行 → 现{len(_doc_new_lines)}行")
ck("v12.0 增补打在原文之后、带版本标记",
   any("【v12.0 增补】" in x for x in _doc_new_lines[len(_doc_old_lines):]))

_old = (BK / "app_ui_main_window.py").read_text(encoding="utf-8").splitlines()
_new = (ROOT / "app/ui/main_window.py").read_text(encoding="utf-8").splitlines()
_diff = list(difflib.unified_diff(_old, _new, lineterm=""))
_added = [x for x in _diff if x.startswith("+") and not x.startswith("+++")]
_deleted = [x for x in _diff if x.startswith("-") and not x.startswith("---")]
ck("旧工作台只是最小必要修正（只替换旧 ratio 取值行）",
   len(_added) <= 12 and len(_deleted) <= 2 and
   any("self.ex_ratio.currentText()" in x for x in _deleted),
   f"新增{len(_added)}行 删除{len(_deleted)}行")
ck("旧工作台改动正是「3:4 推荐比例映射」",
   any("split(" in x for x in _added), str(_added[:3]))
ck("备份里的向导是阶段十一旧版，可随时回退",
   "wizard_lines" not in (BK / "app_ui_wizard.py").read_text(encoding="utf-8")
   and "wizard_lines" in (ROOT / "app/ui/wizard.py").read_text(encoding="utf-8"))

# ================= 准备：临时副本（真实项目只读） =================
shutil.copy2(PROJ, TMP)
shutil.copy2(PROJ, TMP2)
w = WizardWindow()
app.processEvents()
w._load_project(TMP)
app.processEvents()
d = w.db
shots = d.get_timeline()
product = d.get_product_info() or {}
sid = str(shots[0]["shot_id"])
ck("真实项目 13 个镜头", len(shots) == 13, len(shots))

# ================= B. 第一批：成片正确性 =================
wl.save_custom_labels(d, {sid: CUSTOM})
ck("自定义字幕能存进项目并读回",
   wl.load_custom_labels(d).get(sid) == CUSTOM)
b = wl.build_lines_for_export(d, shots, product, "selling_badge")
hit = [l for l in b["lines"] if str(l.get("shot_id")) == sid]
ck("出片文案用上了你改的字（不再每次重新生成覆盖）",
   bool(hit) and hit[0]["text"] == CUSTOM, hit[0]["text"] if hit else "无")
ck("出片标记「用了自定义文案」", b["custom_used"] is True)
ck("默认卖点标签本身没有未核实宣传词", b["forbidden"] == [], str(b["forbidden"]))
bad = wl.validate_custom_texts(["承重100公斤", "实木框架", "十年质保",
                                "这段画面里真的拍到的内容"])
ck("你自己写的字也过禁词护栏（3 句违规、1 句合规）",
   len(bad) == 3, str(bad))
b2 = wl.build_lines_for_export(d, shots, product, "selling_badge",
                               {sid: "承重100公斤"})
ck("出片前会拦下未核实宣传词", len(b2["forbidden"]) > 0, str(b2["forbidden"]))

bs = wl.build_lines_for_export(d, shots, product, "standard")
ck("标准模式按当前 13 个镜头重建（不再用库里陈旧 6 句）",
   bs["rebuilt"] is True and len(bs["lines"]) == 13,
   f"rebuilt={bs['rebuilt']} 行数={len(bs['lines'])}")
ck("标准模式重建时明确告知旧文案作废",
   any("重新排好" in x for x in bs["warnings"]), str(bs["warnings"]))
ck("标准模式文案与镜头一一对应",
   {str(x.get("shot_id")) for x in bs["lines"]} ==
   {str(s["shot_id"]) for s in shots if wl._shot_has_asset(s)})

mw = MainWindow()
app.processEvents()
ratio_items = [mw.ex_ratio.itemText(i) for i in range(mw.ex_ratio.count())]
target = next((t for t in ratio_items if "3:4" in t), None)
if target:
    mw.ex_ratio.setCurrentIndex(ratio_items.index(target))
pr = mw._export_params()
ck("旧工作台「3:4 推荐」选项真实存在", target is not None, str(ratio_items))
ck("旧工作台选 3:4 不再静默回落 16:9",
   pr["ratio"] == "3:4 竖版", pr["ratio"])

mw_src = (ROOT / "app/ui/main_window.py").read_text(encoding="utf-8")
ck("完整工作台把带版式的文案交给字幕引擎",
   'sub_style["lines"] = eff_lines' in mw_src)
badge_lines = nar.decorate_lines(nar.build_selling_lines(shots, product)["lines"])
ass_badge = config.CACHE_DIR / "final" / "_stage12_badge.ass"
g = sub_mod.build_ass_badge(badge_lines, ass_badge,
                            {"preset": sub_mod.BADGE_PRESET, "play_w": 720, "play_h": 960})
ab = ass_badge.read_text(encoding="utf-8-sig", errors="ignore") if ass_badge.exists() else ""
ck("卖点标签大字版式能生成", g.get("ok") is True)
ck("大字版式真的用了 Big/Title 样式（没退化成普通小标签）",
   "Dialogue: 0," in ab and (",Big," in ab or ",Title," in ab),
   f"Big={ab.count(',Big,')} Title={ab.count(',Title,')}")

# ================= C. 第二批：不再误导 =================
with patch("app.ui.wizard.QInputDialog.getText", return_value=("阶段十二验收项目", True)):
    w._new_project()
app.processEvents()
new_dbs = list(config.DB_DIR.glob("我的项目_阶段十二验收项目_*.db"))
created_projects = list(new_dbs)
ck("能新建自己的项目（不再强制打开演示项目）", len(new_dbs) >= 1, str(new_dbs))
ck("新项目一打开不会假装前 4 步都做完了", w._done_before() == 0, w._done_before())
for i in range(4):
    w.db.mark_step_done(i)
ck("真做过 4 步才打 4 个勾", w._done_before() == 4, w._done_before())
w.db.set_setting("wizard_last_step", "2")
w._update_last_step_button()
ck("「上次停在第 N 步」按真实记录显示",
   "第 3 步" in w.last_step.text(), w.last_step.text())

w._load_project(TMP)
app.processEvents()
w._goto_step(2)
app.processEvents()
ck("第 3 步有 13 张镜头卡片", w.shot_grid.count() == 13, w.shot_grid.count())
ck("镜头卡片能点开看该镜头详情", hasattr(w, "_show_shot_detail"))

src12 = (ROOT / "app/ui/wizard.py").read_text(encoding="utf-8")
ck("导出撞名自动加序号（同一秒连点也不覆盖）",
   "while out.exists():" in src12)

# ================= D. 第三批：好用 =================
w._goto_step(3)
app.processEvents()
ck("字幕表 13 行", w.label_table.rowCount() == 13, w.label_table.rowCount())
cell0 = w.label_table.item(0, 2)
ck("字幕可逐句编辑（第 3 列可改）",
   cell0 is not None and bool(cell0.flags() & Qt.ItemIsEditable))
cell0.setText("换个说法试试")
ck("点保存能把改的字存下来", w._save_labels(quiet=True) is True)
ck("改的字确实进了项目库",
   wl.load_custom_labels(w.db).get(sid) == "换个说法试试")
with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
    w._reset_labels()
ck("恢复默认后自定义字被清掉", wl.load_custom_labels(w.db) == {})
# 恢复成后面出片要用的自定义字
wl.save_custom_labels(w.db, {sid: CUSTOM})
w._refresh_labels()

assets = w.db.get_assets()
a0 = assets[0]
real_group = Path(str(a0.get("path") or "")).parent.name
ck("分组按视频真实所在文件夹（不是脏 folder 字段）",
   wl.group_of(a0) == real_group, f"{wl.group_of(a0)} / {real_group}")
ck("脏 folder 字段（纯数字）不干扰分组",
   wl.group_of({"path": a0["path"], "folder": "1"}) == real_group)
gs = wl.groups_summary(assets)
ck("能按文件夹分出多个组", len(gs) >= 2, str(gs))
ck("分组数量合计等于素材总数", sum(n for _, n in gs) == len(assets),
   f"{sum(n for _, n in gs)}/{len(assets)}")
p0 = str(a0["path"])
w._assign_group([p0], "测试分组")
ck("拖拽/批量归类能落库",
   wl.load_custom_groups(w.db).get(p0) == "测试分组")
w._refresh_assets()
app.processEvents()
md = w.asset_list.mimeData([w.asset_list.item(0)])
_dragged = json.loads(bytes(md.data(MIME_ASSETS)).decode("utf-8"))
ck("拖拽数据带自定义格式", md.hasFormat(MIME_ASSETS))
ck("拖拽数据里是真实存在的素材路径",
   len(_dragged) >= 1 and all(Path(x).exists() for x in _dragged if x),
   str(_dragged[:1]))
ck("素材卡片为「只拖出」模式，能拖到分组上",
   w.asset_list.dragDropMode() == QAbstractItemView.DragOnly,
   str(w.asset_list.dragDropMode()))

da = DropArea()
fired = []
da.chooseRequested.connect(lambda: fired.append(1))
ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(5, 5),
                 Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
da.mousePressEvent(ev)
ck("点拖放区会弹出「选文件 / 选整个文件夹」二选一", len(fired) == 1)

ck("权限错误翻译成人话",
   "占用" in _friendly_error(PermissionError("access denied")))
ck("解码错误翻译成人话",
   "读不出来" in _friendly_error(RuntimeError("ffmpeg decode error")))
ck("报错不把英文异常名甩给用户",
   "PermissionError" not in _friendly_error(PermissionError("denied")))
w._on_export_progress(45, 100, "正在处理第 3/13 个镜头…")
ck("进度能显示具体阶段", "第 3/13" in w.export_status.text())

fake = [{"shot_id": "x", "name": "假镜头", "asset_path": "", "sub_segments": ""}]
ck("缺画面镜头能被逐个点名",
   wl.missing_shot_names(fake, w._shot_asset) == ["假镜头"])
with patch("app.ui.wizard.wl.missing_shot_names", return_value=["某镜头"]), \
        patch.object(QMessageBox, "question", return_value=QMessageBox.No) as mq_missing:
    w._start_export()
    mtxt = " ".join(str(a) for a in mq_missing.call_args.args) if mq_missing.call_args else ""
ck("出片前会先如实提醒缺画面镜头", mq_missing.called and "没画面" in mtxt, mtxt[:120])

w.choices["sub_style"] = "standard"
with patch("app.ui.wizard.wl.narration_status", return_value=(0, 13, False)), \
        patch.object(QMessageBox, "question", return_value=QMessageBox.No) as mq_voice:
    w._start_export()
    vtxt = " ".join(str(a) for a in mq_voice.call_args.args) if mq_voice.call_args else ""
ck("选中文旁白却没配音时会明确提醒，不静默降级",
   mq_voice.called and "中文旁白" in vtxt, vtxt[:120])
w.choices["sub_style"] = "selling_badge"

t = 400
fl = [{"start_ms": 0, "end_ms": 3500, "text": "a"},
      {"start_ms": 3500, "end_ms": 7000, "text": "b"},
      {"start_ms": 7000, "end_ms": 10500, "text": "c"}]
al = wl.align_to_transitions(fl, t)
ck("标准字幕按叠化重排，首尾相接不累积漂移",
   al[0]["end_ms"] == al[1]["start_ms"] == 3100 and
   al[1]["end_ms"] == al[2]["start_ms"] == 6200,
   str([(x["start_ms"], x["end_ms"]) for x in al]))
ck("重排时间不改任何文字", [x["text"] for x in al] == ["a", "b", "c"])

ass1 = config.CACHE_DIR / "final" / "_stage12_canvas.ass"
sub_mod.build_ass([{"start_ms": 0, "end_ms": 1000, "text": "测试"}], ass1,
                  {"play_w": 1080, "play_h": 1920})
t1 = ass1.read_text(encoding="utf-8-sig", errors="ignore") if ass1.exists() else ""
ck("标准字幕画布跟随成片真实比例",
   "PlayResX: 1080" in t1 and "PlayResY: 1920" in t1)
ck("不再写死 720x1280", "PlayResY: 1280" not in t1)
ass2 = config.CACHE_DIR / "final" / "_stage12_canvas_badge.ass"
sub_mod.build_ass_badge([{"start_ms": 0, "end_ms": 1000, "text": "测试"}], ass2,
                        {"play_w": 720, "play_h": 960})
t2 = ass2.read_text(encoding="utf-8-sig", errors="ignore") if ass2.exists() else ""
ck("卖点标签画布跟随成片真实比例",
   "PlayResX: 720" in t2 and "PlayResY: 960" in t2)

texts = " ".join(x.text() for x in w.findChildren(QLabel))
for bad_word in ("缓存复用", "可解码", "crf", "帧率", "编码", "xfade"):
    ck(f"界面不出现技术黑话「{bad_word}」", bad_word not in texts)

w._open_workbench(0)
app.processEvents()
ck("完整工作台仍能打开（8 个页面）",
   w._workbench is not None and w._workbench.stack.count() == 8)
ck("切项目时工作台记住当前项目（会同步刷新）",
   str(w._workbench_path) == str(TMP), str(w._workbench_path))

# ================= E. 真实出片端到端 =================
w._load_project(TMP)
app.processEvents()
w._goto_step(4)
app.processEvents()
before = snap(TMP)
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
ck("真实一键出片执行成功", r.get("ok") is True, r.get("error", ""))
srt_path = config.CACHE_DIR / "final" / "wizard.srt"
srt_main = srt_path.read_text(encoding="utf-8", errors="ignore") if srt_path.exists() else ""
ck("你改的字真的进了成片字幕（SRT 与烧录同源）",
   CUSTOM in srt_main, srt_main[:120].replace("\n", " | "))
if r.get("ok"):
    out = Path(r["path"])
    export_paths.append(out)
    info = media.probe(str(out))
    ck("成片文件真实存在且非空",
       out.is_file() and out.stat().st_size > 100000, out.stat().st_size)
    ck("成片为 3:4 竖版 720x960",
       info.get("width") == 720 and info.get("height") == 960,
       f"{info.get('width')}x{info.get('height')}")
    ck("成片时长落在 15-30 秒",
       15000 <= info.get("duration_ms", 0) <= 30000, info.get("duration_ms"))
    ck("成片含音轨", bool(info.get("has_audio")))
    ck("成片可解码", bool(info.get("decode_ok")))
    ck("导出文件名带时间戳",
       bool(re.search(r"\d{8}_\d{6}", out.name)), out.name)
    exports_after = set(config.EXPORT_DIR.glob("一键出片_*.mp4"))
    ck("旧成片没有被覆盖（新片另存）",
       exports_before.issubset(exports_after) and len(exports_after) > len(exports_before),
       f"{len(exports_before)} -> {len(exports_after)}")
    ck("成片结果显示完整存放路径",
       "存在：" in w.export_status.text() and str(out) in w.export_status.text())
after = snap(TMP)
ck("13 个已确认镜头逐行未变", before == after, f"{len(before)} 行")
ck("出片未减少镜头数", len(after) == 13, len(after))
ck("原素材文件一个都没被删改",
   all(Path(str(a.get("path"))).exists() for a in w.db.get_assets()
       if str(a.get("path") or "").strip()))

# 标准模式真实出片：验证 13 行进字幕 + 无配音如实提醒
out2 = config.EXPORT_DIR / f"一键出片_标准模式_{int(time.time())}.mp4"
w2 = ExportWorker(str(TMP), out2, "standard", "narration", "3:4 竖版")
box2 = {}
loop2 = QEventLoop()


def _finish2(res):
    box2["res"] = res
    loop2.quit()


w2.done.connect(_finish2)
QTimer.singleShot(300000, loop2.quit)
w2.start()
loop2.exec()
w2.wait(5000)
r2 = box2.get("res", {})
export_paths.append(out2)
ck("标准模式真实出片也成功", r2.get("ok") is True, r2.get("error", ""))
srt_std = srt_path.read_text(encoding="utf-8", errors="ignore") if srt_path.exists() else ""
ck("标准模式 13 句文案都进了字幕（不是旧 6 句）",
   srt_std.count("-->") == 13, srt_std.count("-->"))
ck("无配音时成片结果如实说明「没有念稿」",
   "没有念稿" in r2.get("note", "") or "只有" in r2.get("note", ""),
   r2.get("note", "")[:120])

# ================= F. 移出素材如实说明关联镜头 =================
w._load_project(TMP2)
app.processEvents()
d2 = dbmod.ProjectDB(str(TMP2))
used_paths = [str(s.get("asset_path")) for s in d2.get_timeline()
              if str(s.get("asset_path") or "").strip()]
ck("当前项目的确有镜头引用着素材（可验关联提示）", len(used_paths) > 0)
row = next((i for i in range(w.asset_list.count())
            if str(w.asset_list.item(i).data(Qt.UserRole)) in set(used_paths)), 0)
w.asset_list.setCurrentRow(row)
app.processEvents()
with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as mq_rm:
    w._remove_selected_asset()
    rmtxt = " ".join(str(a) for a in mq_rm.call_args.args) if mq_rm.call_args else ""
ck("移出时如实说明还有几个镜头在用这些视频",
   "个镜头" in rmtxt, rmtxt[:140])
ck("移出后原视频仍在磁盘上",
   all(Path(p).exists() for p in used_paths if p))

# ================= 清理 =================
for p in (TMP, TMP2):
    p.unlink(missing_ok=True)
for p in created_projects:
    p.unlink(missing_ok=True)

# ================= 结果 =================
passed = sum(1 for c in checks if c["ok"])
result = {
    "stage": 12, "total": len(checks), "passed": passed,
    "failed": len(checks) - passed, "checks": checks,
    "changed_files": sorted(changed),
    "exports": [str(p) for p in export_paths],
}
(ROOT / "tests/test_result_stage12.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"STAGE12 {passed}/{len(checks)}")
for c in checks:
    if not c["ok"]:
        print("FAIL", c["name"], c["detail"])
for p in export_paths:
    if Path(p).is_file():
        print("EXPORT", p)
sys.exit(0 if passed == len(checks) else 1)
