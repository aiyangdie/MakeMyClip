# -*- coding: utf-8 -*-
"""阶段十三 · 向导界面按公开设计语言重做 + 人性化「一步一件事」。

设计规矩来源（只借公开的设计语言与语义命名，不复制代码、不引入第三方库）：
  - Google Material Design 3 Design Kit（Apache 2.0，免费、商用允许）
  - shadcn/ui 语义 token 体系（MIT）
  - Figma Community 免费设计文件（通常 CC BY 4.0，署名即可商用）
落地文件：app/ui/design_tokens.py —— 界面唯一允许出现色值的地方。

用户硬规则一如既往：
1. 不虚构：镜头名、字幕、缩略图全来自真实素材与项目库；自定义字过禁词护栏。
2. 原素材只读：本层不写、不改名、不删除任何素材文件。
3. 用户保留最终决定权：出片前如实提醒，按大按钮才执行。
4. 出片 / 字幕 / 渲染 / 导出链路（ExportWorker 起）本次一字未改。

【阶段十三界面改动】
- 统一语义主题（亮/暗双套、圆角与字号单源派生），清除界面里散落的十几种硬编码颜色。
- 一次只做一件事：每屏一个大标题、一句人话、一个主动作大按钮。
- 说人话：按钮写动作、不蹦技术黑话、没配音如实说、进度写到第几段。
- 能反悔：随时返回上一步、每一步自动存好、专业参数收进「更多」不碍眼。
"""
import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QSize, QMimeData
from PySide6.QtGui import QIcon, QPixmap, QDrag
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QFrame, QFileDialog, QMessageBox, QProgressBar,
    QComboBox, QGridLayout, QScrollArea, QListWidget, QListWidgetItem,
    QAbstractItemView, QSizePolicy, QListView, QApplication,
    QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog, QMenu, QDialog,
)

from .. import config, media, db as dbmod
from ..core import video_editor, narration as nar, subtitle as sub_mod
from ..core import bgm as bgm_mod, audio_mixer, wizard_lines as wl
from ..core.final_exporter import export_final
from ..workers import ImportWorker
from .main_window import MainWindow
from . import design_tokens as dt

STEPS = ["导入素材", "挑镜头", "看片调整", "字幕配音", "一键出片"]
STEP_HINTS = [
    "把视频拖进来就行，原始文件不会动；放错了随时能移出去。",
    "按画面内容排好了顺序；想换哪一段，点开「逐个挑」就行。",
    "节奏已经排好，重要的镜头多停一会儿；点卡片能看详情。",
    "字幕能逐句改，改完点保存，出片就用你写的。",
    "确认一下就按大按钮；出片前会如实提醒没画面和没配音的情况。",
]
RATIO_KEYS = ["3:4 竖版", "9:16 竖屏", "1:1 正方形", "16:9 横屏"]
RATIO_LABELS = ["3:4 竖版（淘宝商详推荐）", "9:16 竖屏", "1:1 正方形", "16:9 横屏"]
DEFAULT_PROJECT = "_stage9_full.db"
MIME_ASSETS = "application/x-mmclips-assets"


def _frame(name="card"):
    """按语义 objectName 造一个卡片，颜色全靠全局 QSS，不写死色值。"""
    f = QFrame()
    f.setObjectName(name)
    return f


def _label(text, name="step_desc", wrap=False):
    lab = QLabel(text)
    lab.setObjectName(name)
    if wrap:
        lab.setWordWrap(True)
    return lab


def _video_files(paths):
    """把拖进来的文件/文件夹展开成真实存在的视频文件列表，去重保序。"""
    out = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for root, _, names in os.walk(p):
                for n in names:
                    if Path(n).suffix.lower() in config.VIDEO_EXTS:
                        out.append(str(Path(root) / n))
        elif p.exists() and p.suffix.lower() in config.VIDEO_EXTS:
            out.append(str(p))
    seen, res = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            res.append(x)
    return res


def _friendly_error(e):
    """把技术异常翻译成人话，不把代码天书摊给用户。"""
    msg = str(e)
    low = msg.lower()
    if "permission" in low or "denied" in low:
        return "有个文件被别的程序占用了，关掉占用它的窗口再试一次。"
    if "no space" in low or "disk" in low:
        return "电脑磁盘空间不够了，清理一点空间再出片。"
    if "ffmpeg" in low or "codec" in low or "decode" in low:
        return "有一段视频读不出来，可能是文件损坏或格式特殊，可在完整工作台里查看。"
    if "memory" in low:
        return "内存不太够，关掉其它大程序再试一次。"
    return f"出了点问题：{msg[:80]}。可以回到上一步重试，或到完整工作台里查看。"


class ClickFrame(QFrame):
    """可点击的卡片容器。"""
    clicked = Signal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class StepBar(QWidget):
    """顶部进度：五个小圆点 + 当前步名，不抢视线；真做过才点亮。"""
    stepClicked = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        self.buttons = []
        for i, text in enumerate(labels):
            b = QPushButton(str(i + 1))
            b.setObjectName("step_todo")
            b.setFixedSize(26, 26)
            b.setToolTip(f"第 {i + 1} 步 · {text}")
            b.clicked.connect(lambda checked=False, k=i: self.stepClicked.emit(k))
            h.addWidget(b)
            self.buttons.append(b)
        self.current_label = _label("第 1 / 5 步", "step_hint")
        h.addSpacing(6)
        h.addWidget(self.current_label)
        h.addStretch(1)
        self.set_state(0, 0)

    def set_state(self, current, done_before):
        for i, b in enumerate(self.buttons):
            b.setObjectName("step_current" if i == current else
                            "step_done" if i < done_before else "step_todo")
            b.setText(str(i + 1))
            b.style().unpolish(b)
            b.style().polish(b)
        self.current_label.setText(
            f"第 {current + 1} / {len(self.buttons)} 步 · {STEPS[current]}")


class GroupList(QListWidget):
    """左侧文件夹分组栏：接受从素材卡片拖过来的视频。"""
    assetsDropped = Signal(str, list)
    newGroupRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setMinimumWidth(150)
        self.setMaximumWidth(230)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_ASSETS):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_ASSETS):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        item = self.itemAt(self._pos(event))
        group = str(item.data(Qt.UserRole) or item.text()) if item else ""
        raw = bytes(event.mimeData().data(MIME_ASSETS)).decode("utf-8", "ignore")
        try:
            paths = json.loads(raw) if raw else []
        except (ValueError, TypeError):
            paths = []
        if item and paths and group not in ("__all__", "__new__"):
            self.assetsDropped.emit(group, paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    @staticmethod
    def _pos(event):
        try:
            return event.position().toPoint()
        except AttributeError:
            return event.pos()


class AssetList(QListWidget):
    """素材卡片区：可多选，卡片能拖到左侧分组。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDefaultDropAction(Qt.CopyAction)

    def mimeData(self, items):
        md = QMimeData()
        paths = [str(it.data(Qt.UserRole) or "") for it in items]
        md.setData(MIME_ASSETS, json.dumps(paths, ensure_ascii=False).encode("utf-8"))
        md.setText("\n".join(it.text() for it in items))
        return md


class DropArea(ClickFrame):
    """把视频拖进来；点一下给「选文件 / 选整个文件夹」二选一。"""
    filesDropped = Signal(list)
    chooseRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(148)
        self.setObjectName("drop")
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(8)
        main = _label("把视频拖到这儿", "drop_main")
        main.setAlignment(Qt.AlignCenter)
        v.addWidget(main)
        sub = _label("比如桌面上那个「素材」文件夹，整个拖进来就行\n"
                     "不用一段一段选，原视频一个都不会动", "drop_sub")
        sub.setAlignment(Qt.AlignCenter)
        v.addWidget(sub)

    def mousePressEvent(self, event):
        self.chooseRequested.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        files = _video_files(paths)
        if files:
            self.filesDropped.emit(files)
        event.acceptProposedAction()


class ExportWorker(QThread):
    """一键出片：真实串起渲染 -> 字幕 -> 音乐 -> 校验，全程在后台跑。"""
    progress = Signal(int, int, str)
    done = Signal(dict)

    def __init__(self, db_path, out_path, sub_style, voice_mode, ratio,
                 custom_labels=None, parent=None):
        super().__init__(parent)
        self.db_path = str(db_path)
        self.out_path = Path(out_path)
        self.sub_style = sub_style
        self.voice_mode = voice_mode
        self.ratio = ratio
        self.custom_labels = custom_labels

    def run(self):
        try:
            db = dbmod.ProjectDB(self.db_path)
            shots = db.get_timeline()
            if not shots:
                self.done.emit({"ok": False, "error": "项目里还没有镜头，请先导入素材并排好镜头。"})
                return
            params = {
                "ratio": self.ratio, "res": "720p", "fps": 30,
                "crf": config.QUALITY_CRF["标准"],
                "transition": config.DEFAULT_TRANSITION,
                "transition_s": config.DEFAULT_TRANSITION_S,
                "min_hold_ms": config.DEFAULT_MIN_HOLD_MS,
                "sub_transition_s": config.DEFAULT_SUB_TRANSITION_S,
            }
            self.progress.emit(2, 100, "正在准备画面…")
            r = video_editor.render_all(
                shots, params, db=db,
                progress_cb=lambda cur, total, sid, cached:
                    self.progress.emit(2 + int(60 * cur / max(1, total)), 100,
                                      f"正在处理第 {cur}/{total} 个镜头…"))
            missing = [e.get("error", "") for e in r.get("errors", [])]
            if not r["segments"]:
                self.done.emit({"ok": False, "error": "没有可用的画面（镜头都还没绑定素材）。"})
                return
            work = config.CACHE_DIR / "wizard"
            work.mkdir(parents=True, exist_ok=True)
            silent = work / "silent.mp4"
            self.progress.emit(64, 100, "正在把画面接起来…")
            c = video_editor.concat_segments(
                r["segments"], silent, transition=params["transition"],
                transition_s=params["transition_s"], crf=params["crf"])
            if not c.get("ok"):
                self.done.emit({"ok": False, "error": "画面拼接失败：" + c.get("error", "")})
                return

            self.progress.emit(70, 100, "正在准备字幕…")
            info = media.probe(str(silent))
            dur = info.get("duration_ms", 0)
            product = db.get_product_info() or {}
            built = wl.build_lines_for_export(db, shots, product,
                                              self.sub_style, self.custom_labels)
            if built["forbidden"]:
                self.done.emit({"ok": False,
                                "error": "字幕里有没核实过的宣传词，已拦下：" + "；".join(built["forbidden"])})
                return
            lines = built["lines"]
            if self.sub_style != "selling_badge" and dur > 0:
                lines = nar.calibrate_to_duration(lines, dur)

            self.progress.emit(78, 100, "正在配音乐…")
            music = ""
            vol = (config.DEFAULT_BGM_VOLUME if self.voice_mode == "bgm_only" else 0.25)
            gen = bgm_mod.synth_bgm(
                dur / 1000.0 + 0.3,
                config.CACHE_DIR / "final" / "wizard_bgm.wav", volume=vol)
            music = gen["path"] if gen.get("ok") else ""

            narration_path = ""
            enable_narration = False
            have_voice, total_line, full_voice = wl.narration_status(db, lines)
            if self.voice_mode != "bgm_only":
                voices = [(ln["voice_path"], ln["start_ms"]) for ln in lines
                          if ln.get("voice_path") and Path(ln["voice_path"]).exists()]
                if voices:
                    nr = audio_mixer.build_narration_track(
                        voices, dur, config.CACHE_DIR / "final" / "wizard_narration.wav",
                        volume=1.0)
                    if nr.get("ok"):
                        narration_path, enable_narration = nr["path"], True

            style = {"font": "Microsoft YaHei", "size": 36, "color": "#FFFFFF",
                     "outline": 2, "alignment": 2}
            if self.sub_style == "selling_badge":
                style["preset"] = sub_mod.BADGE_PRESET
                style["lines"] = lines
            # 【阶段十二】字幕画布按成片真实尺寸自适应，不再写死 720x1280
            style["play_w"] = info.get("width", 720) or 720
            style["play_h"] = info.get("height", 960) or 960
            srt = config.CACHE_DIR / "final" / "wizard.srt"
            self.progress.emit(88, 100, "正在合成成片…")
            res = export_final(
                str(silent), lines, str(srt), str(self.out_path),
                subtitle_style=style, enable_subtitle=True,
                enable_narration=enable_narration, enable_music=bool(music),
                narration_path=narration_path or None, music_path=music or None,
                music_volume=1.0, duck=enable_narration, duration_ms=dur)
            notes = []
            if self.voice_mode != "bgm_only" and not enable_narration:
                notes.append(f"你选了中文旁白，但项目里只有 {have_voice}/{total_line} 句配音，"
                             "这次没有念稿、只有背景音乐（可在完整工作台里生成配音）")
            if missing:
                notes.append(f"有 {len(missing)} 个镜头没有画面，已跳过它们")
            notes.extend(built["warnings"])
            res["note"] = "；".join(notes)
            res["missing_shots"] = missing
            res["custom_used"] = built["custom_used"]
            res["lines_source"] = built["source"]
            self.progress.emit(100, 100, "成片好了")
            self.done.emit(res)
        except Exception as e:  # noqa: BLE001
            self.done.emit({"ok": False, "error": _friendly_error(e)})


class WizardWindow(QMainWindow):
    """五步向导 · 阶段十三人性化重做。旧工作台原样调出，不改动。"""

    def __init__(self):
        super().__init__()
        self.db = None
        self.project_path = None
        self._workbench = None
        self._workbench_path = None
        self._import_worker = None
        self._export_worker = None
        self._asset_rows = []
        self._all_assets = []
        self._current_group = "__all__"
        self._label_rows = []
        self._dark = False
        self.choices = {"sub_style": "selling_badge",
                        "voice_mode": "bgm_only",
                        "ratio": RATIO_KEYS[0]}
        self.setWindowTitle("AI 家具视频剪辑 · 一步一步做商品视频")
        self.resize(1180, 820)
        self._build_ui()
        self.setStyleSheet(dt.qss(self._dark))
        self._load_projects()

    # ---------------- 主题 ----------------
    def _style(self, kind, extra=""):
        """动态生成的卡片/文字按当前主题取色，不在界面里写死色值。"""
        return dt.inline(kind, self._dark, extra)

    def _toggle_theme(self):
        self._dark = not self._dark
        self.setStyleSheet(dt.qss(self._dark))
        self.btn_theme.setText("深色界面" if not self._dark else "浅色界面")
        self.stepbar.set_state(self.stack.currentIndex(), self._done_before())
        self._paint_style_cards()
        if self.stack.currentIndex() == 2:
            self._refresh_shots()

    # ---------------- 界面骨架 ----------------
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("wizard_root")
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 14, 20, 12)
        root.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel("做一条商品视频")
        self.title.setObjectName("step_title")
        head.addWidget(self.title)
        head.addWidget(_label("都存好了", "step_hint"))
        head.addStretch(1)
        self.last_step = QPushButton("从第 1 步开始")
        self.last_step.setObjectName("ghost")
        self.last_step.clicked.connect(self._goto_last_step)
        head.addWidget(self.last_step)
        self.btn_theme = QPushButton("深色界面")
        self.btn_theme.setObjectName("ghost")
        self.btn_theme.clicked.connect(self._toggle_theme)
        head.addWidget(self.btn_theme)
        self.btn_new = QPushButton("新建自己的项目")
        self.btn_new.setObjectName("ghost")
        self.btn_new.clicked.connect(self._new_project)
        head.addWidget(self.btn_new)
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(180)
        self.project_combo.currentTextChanged.connect(self._on_project_changed)
        head.addWidget(self.project_combo)
        b_work = QPushButton("完整工作台")
        b_work.setObjectName("ghost")
        b_work.clicked.connect(lambda: self._open_workbench(0))
        head.addWidget(b_work)
        root.addLayout(head)

        self.stepbar = StepBar(STEPS)
        self.stepbar.stepClicked.connect(self._goto_step)
        root.addWidget(self.stepbar)

        self.stack = QStackedWidget()
        for page in (self._page_import(), self._page_pick(), self._page_shots(),
                     self._page_style(), self._page_export()):
            self.stack.addWidget(page)
        root.addWidget(self.stack, 1)

        foot = QHBoxLayout()
        foot.setSpacing(10)
        self.btn_prev = QPushButton("← 上一步")
        self.btn_prev.setObjectName("ghost")
        self.btn_prev.clicked.connect(
            lambda: self._goto_step(self.stack.currentIndex() - 1))
        foot.addWidget(self.btn_prev)
        self.status_label = QLabel(STEP_HINTS[0])
        self.status_label.setObjectName("step_hint")
        self.status_label.setWordWrap(True)
        foot.addWidget(self.status_label, 1)
        self.btn_next = QPushButton("下一步 →")
        self.btn_next.setObjectName("primary")
        self.btn_next.clicked.connect(
            lambda: self._goto_step(self.stack.currentIndex() + 1))
        foot.addWidget(self.btn_next)
        root.addLayout(foot)

        note = _label("每一步都自动存好，关了软件下次回来还在这儿 · 想改哪一步都能随时回去",
                      "step_hint")
        note.setAlignment(Qt.AlignCenter)
        root.addWidget(note)

        self.setCentralWidget(central)
        self._goto_step(0)

    # ---------------- 第 1 步：导入素材 ----------------
    def _page_import(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(12)
        v.addWidget(_label("第 1 步 · 把视频放进来", "step_title"))
        v.addWidget(_label("放完就能挑镜头了。不用一段一段选，把整个文件夹丢进来就行。"))

        self.drop = DropArea()
        self.drop.chooseRequested.connect(self._drop_choose)
        self.drop.filesDropped.connect(self._start_import)
        v.addWidget(self.drop)

        big = QPushButton("选一个文件夹")
        big.setObjectName("primary")
        big.clicked.connect(self._choose_folder)
        v.addWidget(big, 0, Qt.AlignLeft)

        primary_row = QHBoxLayout()
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setEnabled(False)
        self.btn_select_all.clicked.connect(self._select_all_assets)
        primary_row.addWidget(self.btn_select_all)
        self.btn_remove = QPushButton("移出选中的视频")
        self.btn_remove.setEnabled(False)
        self.btn_remove.setObjectName("danger")
        self.btn_remove.clicked.connect(self._remove_selected_asset)
        primary_row.addWidget(self.btn_remove)
        primary_row.addStretch(1)
        primary_row.addWidget(_label("放错了随时能移出去，电脑里的原视频一个都不会动。",
                                    "step_hint"))
        v.addLayout(primary_row)

        more_btn = QPushButton("想按文件夹分组、或只选某几个文件？点这儿 →")
        more_btn.setObjectName("ghost")
        v.addWidget(more_btn, 0, Qt.AlignLeft)
        self.more_import = QWidget()
        self.more_import.setVisible(False)
        mv = QVBoxLayout(self.more_import)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(8)
        row = QHBoxLayout()
        b1 = QPushButton("选具体的视频文件")
        b1.clicked.connect(self._choose_files)
        b2 = QPushButton("选整个文件夹")
        b2.clicked.connect(self._choose_folder)
        self.btn_to_group = QPushButton("把选中的移到这组")
        self.btn_to_group.setEnabled(False)
        self.btn_to_group.clicked.connect(self._move_selected_to_group)
        b3 = QPushButton("查看全部素材（原来的表格）")
        b3.clicked.connect(lambda: self._open_workbench(1))
        for x in (b1, b2, self.btn_to_group, b3):
            row.addWidget(x)
        row.addStretch(1)
        mv.addLayout(row)
        v.addWidget(self.more_import)
        more_btn.clicked.connect(
            lambda: self.more_import.setVisible(not self.more_import.isVisible()))

        self.import_progress = QProgressBar()
        self.import_progress.setVisible(False)
        v.addWidget(self.import_progress)

        v.addWidget(_label(
            "已经加进来的视频 · 小图是真实画面 · 点一下选中，按住 Ctrl / Shift 可一次选多段",
            "cap", True))
        body = QHBoxLayout()
        self.group_list = GroupList()
        self.group_list.assetsDropped.connect(self._on_assets_dropped)
        self.group_list.newGroupRequested.connect(self._new_group)
        self.group_list.itemClicked.connect(self._on_group_clicked)
        body.addWidget(self.group_list)
        self.asset_list = AssetList()
        self.asset_list.setViewMode(QListView.IconMode)
        self.asset_list.setIconSize(QSize(150, 94))
        self.asset_list.setGridSize(QSize(180, 140))
        self.asset_list.setResizeMode(QListView.Adjust)
        self.asset_list.setMovement(QListView.Static)
        # Qt 的 IconMode / Static 会把拖拽模式改成 DropOnly，必须在布局设置后钉死。
        self.asset_list.setDragDropMode(QAbstractItemView.DragOnly)
        self.asset_list.itemSelectionChanged.connect(self._on_asset_selection)
        self.asset_list.setMinimumHeight(210)
        body.addWidget(self.asset_list, 1)
        v.addLayout(body, 1)
        return w

    # ---------------- 第 2 步：挑镜头 ----------------
    def _page_pick(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(12)
        v.addWidget(_label("第 2 步 · 挑镜头", "step_title"))
        v.addWidget(_label("我们从视频里排好了顺序，就是之前确认过的那些，一段都没改。"))

        metric = _frame("subtle")
        mh = QHBoxLayout(metric)
        mh.setContentsMargins(16, 12, 16, 12)
        mh.addWidget(_label("已排好的镜头", "metric_label"))
        mh.addWidget(_label("从整体亮相、三色灯、灯杆伸缩，到拉手和柜脚，顺序都排好了",
                            "step_desc", True), 1)
        v.addWidget(metric)

        big = QPushButton("就用这些镜头，下一步 →")
        big.setObjectName("primary")
        big.clicked.connect(lambda: self._goto_step(2))
        v.addWidget(big, 0, Qt.AlignLeft)

        self.pick_list = QListWidget()
        self.pick_list.itemClicked.connect(self._on_pick_clicked)
        v.addWidget(self.pick_list, 1)
        self.pick_desc = _label("按画面内容排好了顺序。", "step_hint", True)
        v.addWidget(self.pick_desc)
        b = QPushButton("想换镜头 / 改长短？去完整工作台 →")
        b.setObjectName("ghost")
        b.clicked.connect(lambda: self._open_workbench(5))
        v.addWidget(b, 0, Qt.AlignLeft)
        return w

    # ---------------- 第 3 步：看片调整 ----------------
    def _page_shots(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(12)
        v.addWidget(_label("第 3 步 · 节奏", "step_title"))
        v.addWidget(_label("重要的镜头多停一会儿，过渡的快一点，都已经排好了，您不用管。"))

        cards = QHBoxLayout()
        cards.setSpacing(12)
        for name, value in (("总长", "按画面排"), ("画幅", "竖版"), ("转场", "自然")):
            box = _frame("subtle")
            bv = QVBoxLayout(box)
            bv.setContentsMargins(16, 10, 16, 10)
            bv.addWidget(_label(name, "metric_label"))
            bv.addWidget(_label(value, "metric_num"))
            cards.addWidget(box)
        v.addLayout(cards)

        big = QPushButton("就这样，下一步 →")
        big.setObjectName("primary")
        big.clicked.connect(lambda: self._goto_step(3))
        v.addWidget(big, 0, Qt.AlignLeft)

        v.addWidget(_label("每张小图都是从真实素材里抽出来的；点卡片能看详情。", "cap"))
        self.shot_scroll = QScrollArea()
        self.shot_scroll.setWidgetResizable(True)
        self.shot_host = QWidget()
        self.shot_grid = QGridLayout(self.shot_host)
        self.shot_grid.setSpacing(12)
        self.shot_scroll.setWidget(self.shot_host)
        v.addWidget(self.shot_scroll, 1)
        return w

    # ---------------- 第 4 步：字幕配音 ----------------
    def _page_style(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(12)
        v.addWidget(_label("第 4 步 · 字幕和声音", "step_title"))
        v.addWidget(_label("字幕按画面写好了，没写没核实过的宣传词；您改过的字，出片一定用您的。"))

        big = QPushButton("不改，用这版 →")
        big.setObjectName("primary")
        big.clicked.connect(lambda: self._goto_step(4))
        v.addWidget(big, 0, Qt.AlignLeft)

        warn = _frame("warning")
        wv = QVBoxLayout(warn)
        wv.setContentsMargins(14, 10, 14, 10)
        wv.addWidget(_label(
            "中文旁白需要先在「完整工作台 → 音频字幕」里生成配音；"
            "没配音时成片只有音乐，我们会如实告诉您，不会假装念了稿。",
            "warning_text", True))
        v.addWidget(warn)

        self.style_cards = []
        for key, title, desc in [
            ("selling_badge", "卖点标签 + 背景音乐（推荐）",
             "短标签字幕、不念稿、只有平稳背景音乐；对照您给的参考片风格"),
            ("standard", "完整句字幕 + 中文旁白",
             "完整句白字 + 中文配音；若项目里还没生成配音，出片前会明确提醒您"),
        ]:
            card = ClickFrame()
            card.setMinimumHeight(66)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            cv = QVBoxLayout(card)
            cv.addWidget(_label(title, "headline"))
            cv.addWidget(_label(desc, "step_desc", True))
            card.clicked.connect(lambda k=key: self._choose_style(k))
            v.addWidget(card)
            self.style_cards.append((key, card))
        self._paint_style_cards()

        lab_row = QHBoxLayout()
        self.btn_save_labels = QPushButton("保存文案")
        self.btn_save_labels.setObjectName("primary")
        self.btn_save_labels.clicked.connect(self._save_labels)
        self.btn_reset_labels = QPushButton("恢复默认文案")
        self.btn_reset_labels.clicked.connect(self._reset_labels)
        lab_row.addWidget(self.btn_save_labels)
        lab_row.addWidget(self.btn_reset_labels)
        lab_row.addStretch(1)
        self.label_hint = _label("改过的字会存进项目，出片不会再用固定那几句。", "step_hint")
        lab_row.addWidget(self.label_hint)
        v.addLayout(lab_row)

        self.label_table = QTableWidget()
        self.label_table.setColumnCount(4)
        self.label_table.setHorizontalHeaderLabels(
            ["#", "镜头", "字幕上的字（可直接改）", "约几秒"])
        self.label_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.label_table.setColumnWidth(0, 36)
        self.label_table.setColumnWidth(1, 170)
        self.label_table.setColumnWidth(3, 70)
        self.label_table.verticalHeader().setVisible(False)
        self.label_table.setMinimumHeight(190)
        v.addWidget(self.label_table, 1)

        more = QPushButton("更多设置（画面比例）")
        more.setObjectName("ghost")
        more.clicked.connect(lambda: self.more_box.setVisible(not self.more_box.isVisible()))
        v.addWidget(more, 0, Qt.AlignLeft)
        self.more_box = QWidget()
        self.more_box.setVisible(False)
        mh = QHBoxLayout(self.more_box)
        mh.addWidget(_label("画面比例："))
        self.ratio_combo = QComboBox()
        self.ratio_combo.addItems(RATIO_LABELS)
        self.ratio_combo.currentIndexChanged.connect(self._on_ratio)
        mh.addWidget(self.ratio_combo, 1)
        mh.addWidget(_label("淘宝商详推荐 3:4，其他比例也随时能换回来", "step_hint"))
        v.addWidget(self.more_box)
        return w

    # ---------------- 第 5 步：一键出片 ----------------
    def _page_export(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(12)
        v.addWidget(_label("第 5 步 · 出片", "step_title"))
        v.addWidget(_label("都齐了。出好的片子会单独存一份，不会盖掉以前的，"
                           "出完点一下就能打开文件夹。"))

        box = _frame("box")
        bv = QVBoxLayout(box)
        bv.setContentsMargins(16, 12, 16, 12)
        self.summary = _label("正在读取项目…", "step_desc", True)
        bv.addWidget(self.summary)
        self.summary_note = _label("这些参数都帮您选好了，想改回第 4 步就行。", "step_hint")
        bv.addWidget(self.summary_note)
        v.addWidget(box)

        self.btn_export = QPushButton("一键出片")
        self.btn_export.setObjectName("primary")
        self.btn_export.clicked.connect(self._start_export)
        v.addWidget(self.btn_export, 0, Qt.AlignLeft)

        self.export_progress = QProgressBar()
        self.export_progress.setVisible(False)
        v.addWidget(self.export_progress)
        self.export_status = QLabel("")
        self.export_status.setObjectName("success_text")
        self.export_status.setWordWrap(True)
        v.addWidget(self.export_status)
        res_row = QHBoxLayout()
        self.btn_open_result = QPushButton("打开成片")
        self.btn_open_result.setVisible(False)
        self.btn_open_result.clicked.connect(self._open_result)
        self.btn_open_folder = QPushButton("打开成片所在文件夹")
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_result_folder)
        res_row.addWidget(self.btn_open_result)
        res_row.addWidget(self.btn_open_folder)
        res_row.addStretch(1)
        v.addLayout(res_row)
        b_back = QPushButton("想改样式？回到第 4 步")
        b_back.setObjectName("ghost")
        b_back.clicked.connect(lambda: self._goto_step(3))
        v.addWidget(b_back, 0, Qt.AlignLeft)
        v.addStretch(1)
        return w

    # ---------------- 数据 ----------------
    def _load_projects(self, initial=None):
        dbs = [p for p in config.DB_DIR.glob("*.db")
               if not p.stem.startswith(("_test", "_gui", "_stage1", "_stage2",
                                        "_stage3", "_stage4", "_stage5", "_stage6",
                                        "_stage7", "_stage8", "_stage11"))]
        dbs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        preferred = config.DB_DIR / DEFAULT_PROJECT
        if initial:
            ordered = [Path(initial)] + [p for p in dbs if p.name != Path(initial).name]
        elif preferred.exists():
            ordered = [preferred] + [p for p in dbs if p.name != preferred.name]
        else:
            ordered = dbs
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        for p in ordered:
            label = p.stem
            try:
                d = dbmod.ProjectDB(str(p))
                prod = (d.get_product_info() or {}).get("name", "").strip()
                meta = d.get_meta() or {}
                nice = prod or meta.get("name") or p.stem
                label = f"{nice}（{p.stem}）" if nice != p.stem else p.stem
                if p.name == DEFAULT_PROJECT:
                    label += " · 演示样例"
            except Exception:  # noqa: BLE001
                pass
            self.project_combo.addItem(label, str(p))
        self.project_combo.blockSignals(False)
        if self.project_combo.count():
            self._load_project(self.project_combo.itemData(0))
        else:
            self.status_label.setText("还没有项目，点右上角「新建自己的项目」就能开始。")

    def _on_project_changed(self, _text):
        p = self.project_combo.currentData()
        if p:
            self._load_project(p)

    def _load_project(self, path):
        try:
            p = Path(path)
            if not p.is_absolute():
                p = config.DB_DIR / p
            self.db = dbmod.ProjectDB(str(p))
            self.project_path = p
            self._current_group = "__all__"
            prod = (self.db.get_product_info() or {}).get("name", "").strip()
            meta = self.db.get_meta() or {}
            nice = prod or meta.get("name") or p.stem
            self.title.setText(f"做一条商品视频 · {nice}")
            self._refresh_assets()
            self._refresh_groups()
            self._refresh_pick()
            self._refresh_labels()
            self._refresh_summary()
            self._update_last_step_button()
            self.status_label.setText(STEP_HINTS[self.stack.currentIndex()])
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "项目打不开", _friendly_error(e))

    def _new_project(self):
        name, ok = QInputDialog.getText(
            self, "新建自己的项目", "给这个商品起个名字（只用于项目里显示，不会编进字幕）：")
        if not ok or not name.strip():
            return
        safe = re.sub(r"[^\w\u4e00-\u9fff-]", "_", name.strip())[:40]
        p = config.DB_DIR / f"我的项目_{safe}_{int(time.time())}.db"
        if p.exists():
            QMessageBox.information(self, "重名了", "请稍一秒再试，或换个名字。")
            return
        d = dbmod.ProjectDB(str(p))
        d.set_product_info({"name": name.strip()})
        self._load_projects(initial=str(p))
        self._goto_step(0)
        self.status_label.setText(
            f"新项目「{name.strip()}」建好了。先把视频拖进来，再去完整工作台排镜头。")

    def _refresh_assets(self):
        self.asset_list.clear()
        self._asset_rows = []
        if not self.db:
            return
        self._all_assets = self.db.get_assets()
        ov = wl.load_custom_groups(self.db)
        for a in self._all_assets:
            if self._current_group != "__all__" and wl.group_of(a, ov) != self._current_group:
                continue
            self._asset_rows.append(a)
            tp = a.get("thumb_path") or ""
            if not tp or not Path(tp).exists():
                tp = media.make_thumb(a.get("path", ""), a.get("duration_ms", 0), 320)
            icon = QIcon(tp) if tp and Path(tp).exists() else QIcon()
            item = QListWidgetItem(
                icon, f"{a.get('filename', '')}\n{media.format_duration(a.get('duration_ms', 0))}")
            item.setSizeHint(QSize(180, 140))
            item.setData(Qt.UserRole, a.get("path", ""))
            self.asset_list.addItem(item)
        if hasattr(self, "btn_select_all"):
            self.btn_select_all.setEnabled(self.asset_list.count() > 0)
            self.btn_select_all.setText("全选")

    def _refresh_groups(self):
        self.group_list.clear()
        if not self.db:
            return
        ov = wl.load_custom_groups(self.db)
        extra = wl.load_extra_groups(self.db)
        all_item = QListWidgetItem(f"全部视频（{len(self._all_assets)}）")
        all_item.setData(Qt.UserRole, "__all__")
        self.group_list.addItem(all_item)
        for name, cnt in wl.groups_summary(self._all_assets, ov, extra):
            it = QListWidgetItem(f"{name}（{cnt}）")
            it.setData(Qt.UserRole, name)
            self.group_list.addItem(it)
        new_item = QListWidgetItem("＋ 新建分组")
        new_item.setData(Qt.UserRole, "__new__")
        self.group_list.addItem(new_item)
        for i in range(self.group_list.count()):
            it = self.group_list.item(i)
            if str(it.data(Qt.UserRole)) == self._current_group:
                self.group_list.setCurrentItem(it)
                break

    def _on_group_clicked(self, item):
        group = str(item.data(Qt.UserRole) or "__all__")
        if group == "__new__":
            self._new_group()
            return
        self._current_group = group
        self.group_list.setCurrentItem(item)
        self._refresh_assets()
        label = "全部视频" if group == "__all__" else f"「{group}」"
        self.status_label.setText(f"现在看的是{label}，共 {self.asset_list.count()} 段。")

    def _on_assets_dropped(self, group, paths):
        self._assign_group(paths, group)

    def _move_selected_to_group(self):
        group = self._current_group
        if group == "__all__":
            QMessageBox.information(self, "先选一个分组",
                                    "先在左边点一个分组，再点这个按钮；或直接把卡片拖到分组上。")
            return
        items = self.asset_list.selectedItems()
        if not items:
            QMessageBox.information(self, "先选视频", "先点选要归类的视频卡片，再点这个按钮。")
            return
        self._assign_group([str(it.data(Qt.UserRole) or "") for it in items], group)

    def _assign_group(self, paths, group):
        if not self.db:
            return
        ov = wl.load_custom_groups(self.db)
        for p in paths:
            if p:
                ov[p] = group
        wl.save_custom_groups(self.db, ov)
        self._refresh_assets()
        self._refresh_groups()
        self.status_label.setText(
            f"已把 {len([p for p in paths if p])} 段视频归到「{group}」，电脑里的原视频没动。")

    def _new_group(self):
        name, ok = QInputDialog.getText(self, "新建分组", "给这个分组起个名字：")
        if not ok or not name.strip():
            return
        names = wl.load_extra_groups(self.db)
        if name.strip() not in names:
            names.append(name.strip())
            wl.save_extra_groups(self.db, names)
        self._current_group = name.strip()
        self._refresh_assets()
        self._refresh_groups()
        self.status_label.setText(
            f"分组「{name.strip()}」建好了。把右边的视频卡片拖到这个分组上，或选中卡片点「把选中的移到这组」。")

    def _refresh_pick(self):
        self.pick_list.clear()
        if not self.db:
            return
        shots = self.db.get_timeline()
        for i, s in enumerate(shots, 1):
            sec = (s.get("target_ms") or 0) / 1000.0
            label = f"{i}.  {s.get('name', '')}    ·    约 {sec:.1f} 秒" if sec else \
                    f"{i}.  {s.get('name', '')}"
            self.pick_list.addItem(label)
        self.pick_desc.setText(
            f"按画面内容排好了 {len(shots)} 个镜头。点某一行看它用的视频；"
            "想换镜头、改长短，点下面按钮去完整工作台。")

    def _on_pick_clicked(self, item):
        i = self.pick_list.row(item)
        shots = self.db.get_timeline() if self.db else []
        if 0 <= i < len(shots):
            s = shots[i]
            ap = self._shot_asset(s)
            fn = Path(ap).name if ap else "（还没画面）"
            self.pick_desc.setText(
                f"第 {i + 1} 个镜头「{s.get('name', '')}」用的视频：{fn}"
                f" · 约 {(s.get('target_ms') or 0) / 1000.0:.1f} 秒。")

    def _shot_asset(self, shot):
        ap = (shot.get("asset_path") or "").strip()
        if ap:
            return ap
        raw = shot.get("sub_segments") or ""
        subs = []
        if isinstance(raw, list):
            subs = raw
        elif isinstance(raw, str) and raw.strip():
            try:
                subs = json.loads(raw)
            except (ValueError, TypeError):
                subs = []
        if subs:
            return (subs[0].get("asset_path") or subs[0].get("asset_hint") or "").strip()
        return ""

    def _shot_thumb(self, shot):
        ap = self._shot_asset(shot)
        if not ap or not Path(ap).exists():
            return ""
        key = hashlib.md5(f"{ap}|{shot.get('start_ms', 0)}".encode("utf-8")).hexdigest()[:12]
        out = config.CACHE_DIR / "wizard_thumbs" / f"{key}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            return str(out)
        t = max(0.0, (shot.get("start_ms") or 0) / 1000.0 + 0.15)
        try:
            r = media._run(
                ["-y", "-ss", f"{t:.3f}", "-i", ap, "-frames:v", "1",
                 "-vf", "scale=240:-2", "-q:v", "4", str(out)], timeout=60)
            if r.returncode == 0 and out.exists():
                return str(out)
        except Exception:  # noqa: BLE001
            pass
        return media.make_thumb(ap, 1000, 240) or ""

    def _refresh_shots(self):
        while self.shot_grid.count():
            it = self.shot_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not self.db:
            return
        shots = self.db.get_timeline()
        for i, s in enumerate(shots):
            card = ClickFrame()
            card.setFixedHeight(150)
            missing = not self._shot_asset(s)
            card.setStyleSheet(self._style("card_miss" if missing else "card"))
            cv = QVBoxLayout(card)
            cv.setContentsMargins(8, 8, 8, 8)
            pic = QLabel()
            pic.setAlignment(Qt.AlignCenter)
            pic.setFixedHeight(94)
            if missing:
                pic.setText("还没有画面")
                pic.setStyleSheet(self._style("missing_pic"))
            else:
                tp = self._shot_thumb(s)
                if tp and Path(tp).exists():
                    pic.setPixmap(QPixmap(tp).scaled(
                        210, 94, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    pic.setText("画面读取中")
                    pic.setStyleSheet(self._style("loading_pic"))
            cv.addWidget(pic)
            name = QLabel(s.get("name", ""))
            name.setAlignment(Qt.AlignCenter)
            name.setStyleSheet(self._style("shot_name_miss" if missing else "shot_name"))
            cv.addWidget(name)
            sec = (s.get("target_ms") or 0) / 1000.0
            sub = QLabel("点这里看详情 / 去补画面" if missing else (f"约 {sec:.1f} 秒" if sec else ""))
            sub.setAlignment(Qt.AlignCenter)
            sub.setStyleSheet(self._style("shot_sub"))
            cv.addWidget(sub)
            card.clicked.connect(lambda shot=s: self._show_shot_detail(shot))
            self.shot_grid.addWidget(card, i // 4, i % 4)
            QApplication.processEvents()

    def _show_shot_detail(self, shot):
        shots = self.db.get_timeline() if self.db else []
        idx = next((i + 1 for i, s in enumerate(shots)
                    if s.get("shot_id") == shot.get("shot_id")), 0)
        ap = self._shot_asset(shot)
        fn = Path(ap).name if ap else "（这段还没画面，需要补）"
        sec = (shot.get("target_ms") or 0) / 1000.0
        box = QMessageBox(self)
        box.setWindowTitle("这个镜头")
        box.setText(f"第 {idx} 个镜头「{shot.get('name', '')}」\n"
                    f"画面来自：{fn}\n约 {sec:.1f} 秒\n\n"
                    "要换画面或改长短，点下面的按钮去完整工作台，在那里只动这一个镜头。")
        go = box.addButton("去完整工作台调整这个镜头", QMessageBox.AcceptRole)
        box.addButton("先关掉", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is go:
            self._open_workbench(5)

    def _refresh_labels(self):
        self.label_table.setRowCount(0)
        self._label_rows = []
        if not self.db:
            return
        shots = self.db.get_timeline()
        product = self.db.get_product_info() or {}
        if self.choices["sub_style"] == "selling_badge":
            base = nar.build_selling_lines(shots, product)["lines"]
        else:
            base = nar.build_all(shots, product)["lines"]
        custom = wl.load_custom_labels(self.db)
        self._label_rows = base
        self.label_table.setRowCount(len(base))
        for i, ln in enumerate(base):
            key = str(ln.get("shot_id") or "")
            txt = custom.get(key, ln.get("text", ""))
            sec = max(0, int(ln.get("end_ms", 0)) - int(ln.get("start_ms", 0))) / 1000.0
            cells = [QTableWidgetItem(str(i + 1)),
                     QTableWidgetItem(str(ln.get("name", ""))),
                     QTableWidgetItem(str(txt)),
                     QTableWidgetItem(f"{sec:.1f}")]
            for j, cell in enumerate(cells):
                if j != 2:
                    cell.setFlags(Qt.ItemIsEnabled)
                self.label_table.setItem(i, j, cell)
        n = len(custom)
        self.label_hint.setText(
            f"已存 {n} 句你自己写的字，出片会用这些。" if n else
            "改过的字会存进项目，出片不会再用固定那几句。")

    def _save_labels(self, quiet=False):
        if not self.db or not self._label_rows:
            return True
        mapping = {}
        for i, ln in enumerate(self._label_rows):
            cell = self.label_table.item(i, 2)
            if not cell:
                continue
            txt = str(cell.text()).strip()
            key = str(ln.get("shot_id") or "")
            if txt != str(ln.get("text", "")).strip():
                mapping[key] = txt
        bad = wl.validate_custom_texts(mapping.values())
        if bad:
            QMessageBox.warning(self, "这几个词不能用",
                                "字幕里不能写没核实过的宣传词：\n\n" + "；".join(bad[:6]) +
                                "\n\n请改成画面里真的能看到的内容。")
            return False
        wl.save_custom_labels(self.db, mapping)
        self._refresh_labels()
        self._refresh_summary()
        if not quiet:
            self.status_label.setText(
                f"已保存 {len(mapping)} 句自己写的字幕，出片就用你写的。")
        return True

    def _reset_labels(self):
        if not self.db:
            return
        if QMessageBox.question(
                self, "恢复默认", "把字幕文字全部改回默认那几句？你自己写的字会被清掉。") \
                != QMessageBox.Yes:
            return
        wl.save_custom_labels(self.db, {})
        self._refresh_labels()
        self._refresh_summary()
        self.status_label.setText("字幕文字已恢复默认，出片会重新用默认文案。")

    def _refresh_summary(self):
        if not self.db:
            return
        shots = self.db.get_timeline()
        usable = sum(1 for s in shots if self._shot_asset(s))
        missing = len(shots) - usable
        style = "卖点标签字幕 + 背景音乐" if self.choices["sub_style"] == "selling_badge" \
            else "完整句字幕 + 中文旁白"
        ratio = RATIO_LABELS[RATIO_KEYS.index(self.choices["ratio"])]
        custom = wl.load_custom_labels(self.db)
        parts = [f"{ratio} · 约 30 秒 · {usable} 个镜头有画面 · {style}",
                 f"字幕：{'你改过 ' + str(len(custom)) + ' 句' if custom else '默认文案'}"]
        if missing:
            parts.append(f"还有 {missing} 个镜头没画面，出片会跳过它们")
        if self.choices["sub_style"] == "standard":
            built = wl.build_lines_for_export(
                self.db, shots, self.db.get_product_info() or {}, "standard")
            have, total, full = wl.narration_status(self.db, built["lines"])
            parts.append("配音：齐全，会念稿" if full else
                         f"配音：只有 {have}/{total} 句，出片前会提醒你（没有念稿就只有音乐）")
        self.summary.setText("\n".join(parts))
        self.summary_note.setText("画面来自你导入的真实素材；字幕只写镜头里真的拍到的内容。")
        self.btn_open_result.setVisible(False)
        self.btn_open_folder.setVisible(False)

    def _done_before(self):
        """只按真实操作过的步骤打勾，不再一打开就全打勾。"""
        if not self.db:
            return 0
        st = self.db.get_step_state()
        n = 0
        for i in range(4):
            if st.get(i):
                n = i + 1
            else:
                break
        return n

    def _update_last_step_button(self):
        if not self.db:
            self.last_step.setText("从第 1 步开始")
            return
        idx = self.db.get_last_step()
        st = self.db.get_step_state()
        if not st:
            self.last_step.setText("从第 1 步开始")
        else:
            self.last_step.setText(f"上次停在第 {idx + 1} 步「{STEPS[idx]}」")
        self.last_step.setProperty("step", idx)

    def _goto_last_step(self):
        self._goto_step(int(self.last_step.property("step") or 0))

    # ---------------- 交互 ----------------
    def _goto_step(self, idx):
        idx = max(0, min(4, int(idx)))
        self.stack.setCurrentIndex(idx)
        self.stepbar.set_state(idx, self._done_before())
        self.btn_prev.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < 4)
        self.status_label.setText(STEP_HINTS[idx])
        if self.db:
            self.db.set_setting("wizard_last_step", str(idx))
            self._update_last_step_button()
        if idx == 2:
            self._refresh_shots()
        if idx == 3:
            self._refresh_labels()
        if idx == 4:
            self._refresh_summary()

    def _choose_style(self, key):
        self.choices["sub_style"] = key
        self.choices["voice_mode"] = "bgm_only" if key == "selling_badge" else "narration"
        self._paint_style_cards()
        self._refresh_labels()
        self._refresh_summary()
        self._mark_done(3)

    def _paint_style_cards(self):
        for key, card in self.style_cards:
            card.setStyleSheet(self._style("card_on" if key == self.choices["sub_style"] else "card"))

    def _on_ratio(self, idx):
        if 0 <= idx < len(RATIO_KEYS):
            self.choices["ratio"] = RATIO_KEYS[idx]
            self._refresh_summary()

    def _mark_done(self, idx):
        if self.db:
            self.db.mark_step_done(idx)
            self.stepbar.set_state(self.stack.currentIndex(), self._done_before())

    def _open_workbench(self, row=0):
        try:
            if self._workbench is None:
                self._workbench = MainWindow()
            # 【阶段十二】切了项目就把工作台同步刷新，避免还显示上一个项目的数据
            cur = str(self.project_path) if self.project_path else ""
            if cur and cur != self._workbench_path:
                self._workbench._load_project(cur)
                self._workbench_path = cur
            self._workbench.showNormal()
            self._workbench.raise_()
            self._workbench.activateWindow()
            self._workbench.nav.setCurrentRow(row)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "打不开完整工作台", _friendly_error(e))

    def _on_asset_selection(self):
        sel = self.asset_list.selectedItems()
        n = len(sel)
        if hasattr(self, "btn_remove"):
            self.btn_remove.setEnabled(n > 0)
            self.btn_remove.setText(
                "移出选中的视频" if n <= 1 else f"移出选中的 {n} 段视频")
        if hasattr(self, "btn_to_group"):
            self.btn_to_group.setEnabled(n > 0 and self._current_group != "__all__")
        if hasattr(self, "btn_select_all"):
            total = self.asset_list.count()
            all_selected = total > 0 and n == total
            self.btn_select_all.setText("取消全选" if all_selected else "全选")

    def _select_all_assets(self):
        total = self.asset_list.count()
        if total == 0:
            return
        if len(self.asset_list.selectedItems()) == total:
            self.asset_list.clearSelection()
        else:
            self.asset_list.selectAll()

    def _remove_selected_asset(self):
        """从项目里移出选中的素材（可多选）。只删数据库记录，绝不删磁盘原文件。"""
        items = self.asset_list.selectedItems()
        if not items or not self.db or not self._asset_rows:
            return
        rows = []
        for it in items:
            r = self.asset_list.row(it)
            if 0 <= r < len(self._asset_rows):
                rows.append(self._asset_rows[r])
        if not rows:
            return
        n = len(rows)
        path_set = {a.get("path", "") for a in rows}
        used = self.db.count_shots_using_paths(path_set)
        if n == 1:
            head = f"把「{rows[0].get('filename', '')}」从这个项目里移出？"
        else:
            names = "、".join(a.get("filename", "") for a in rows[:4])
            more = "" if n <= 4 else f" 等 {n} 段"
            head = f"把选中的 {n} 段视频从这个项目里移出？\n\n{names}{more}"
        msg = (head + "\n\n"
               "只移出项目里的记录，不会删除你电脑上的原视频文件。")
        if used:
            msg += (f"\n\n如实说明：还有 {used} 个镜头正用到这些视频。"
                    "移出后这些镜头仍能照常出片（原视频还在），但素材库里不再列出它们，"
                    "关联会断开；以后想换镜头，请到完整工作台重新绑定。")
        if QMessageBox.question(self, "确认移出", msg) != QMessageBox.Yes:
            return
        done, errs = [], []
        for a in rows:
            try:
                self.db.delete_asset(a["id"])
                done.append(a.get("filename", ""))
            except Exception as e:  # noqa: BLE001
                errs.append(f"{a.get('filename', '')}：{e}")
        self._refresh_assets()
        self._refresh_groups()
        self._on_asset_selection()
        if errs:
            QMessageBox.warning(self, "部分没移成", "\n".join(errs[:5]))
        if len(done) == 1:
            self.status_label.setText(
                f"已移出「{done[0]}」，电脑里的原视频没动。")
        else:
            self.status_label.setText(
                f"已移出 {len(done)} 段视频，电脑里的原视频没动。")

    def _drop_choose(self):
        m = QMenu(self)
        a1 = m.addAction("选具体的视频文件")
        a2 = m.addAction("选整个文件夹（连子文件夹一起）")
        act = m.exec(self.drop.mapToGlobal(self.drop.rect().center()))
        if act is a1:
            self._choose_files()
        elif act is a2:
            self._choose_folder()

    def _choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选视频文件", str(Path.home() / "Desktop"),
            "视频文件 (*.mp4 *.mov *.m4v *.avi *.mkv *.wmv *.flv *.webm)")
        if files:
            self._start_import(files)

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "选整个文件夹", str(Path.home() / "Desktop"))
        if folder:
            files = _video_files([folder])
            if files:
                self._start_import(files)
            else:
                QMessageBox.information(self, "没找到视频", "这个文件夹里没有找到视频文件。")

    def _start_import(self, files):
        if not self.db:
            QMessageBox.information(self, "先建项目", "请先点右上角「新建自己的项目」。")
            return
        files = _video_files(files)
        if not files:
            return
        self.import_progress.setVisible(True)
        self.import_progress.setRange(0, len(files))
        self.import_progress.setValue(0)
        w = ImportWorker(files, self)
        self._import_worker = w

        def on_prog(cur, total, name):
            self.import_progress.setValue(cur)
            self.status_label.setText(f"正在读取第 {cur}/{total} 段视频…")

        def on_one(info):
            info["thumb_path"] = info.get("thumb_path", "") or ""
            self.db.add_asset(info)

        def on_done(ok, fail):
            self.import_progress.setVisible(False)
            self._refresh_assets()
            self._refresh_groups()
            tail = f"，有 {fail} 段读不出来（可在完整工作台里查看）" if fail else "，都认出来了"
            self.status_label.setText(f"加进来 {ok} 段视频{tail}。已按原文件夹分好组。")
            self._import_worker = None
            self._mark_done(0)

        w.progress.connect(on_prog)
        w.one_done.connect(on_one)
        w.all_done.connect(on_done)
        w.start()

    def _start_export(self):
        if not self.db or not self.project_path:
            QMessageBox.information(self, "先打开项目", "请先打开或新建一个项目再出片。")
            return
        # 出片前把第 4 步里可能还没点保存的编辑落库（有未核实词会拦下）
        if hasattr(self, "label_table") and not self._save_labels(quiet=True):
            self._goto_step(3)
            return
        shots = self.db.get_timeline()
        miss = wl.missing_shot_names(shots, self._shot_asset)
        if miss and QMessageBox.question(
                self, "还有镜头没画面",
                f"有 {len(miss)} 个镜头还没绑定视频：{'、'.join(miss[:5])}"
                + ("…" if len(miss) > 5 else "") +
                "。\n\n出片会跳过它们（成片会短一点）。要继续吗？") != QMessageBox.Yes:
            return
        if self.choices["sub_style"] == "standard":
            built = wl.build_lines_for_export(
                self.db, shots, self.db.get_product_info() or {}, "standard")
            have, total, full = wl.narration_status(self.db, built["lines"])
            if not full and QMessageBox.question(
                    self, "中文旁白还没配音",
                    f"你选了「完整句字幕 + 中文旁白」，但项目里只有 {have}/{total} 句配音。\n\n"
                    "这次成片不会有念稿、只有背景音乐。要继续吗？"
                    "（想有念稿，可以去完整工作台的「音频字幕」页生成配音）") \
                    != QMessageBox.Yes:
                return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag = "参考片风格" if self.choices["sub_style"] == "selling_badge" else "标准模式"
        # 【阶段十二】秒级时间戳在同一秒连点两次仍可能覆盖旧片；撞名就自动加序号
        out = config.EXPORT_DIR / f"一键出片_{tag}_{stamp}.mp4"
        k = 1
        while out.exists():
            out = config.EXPORT_DIR / f"一键出片_{tag}_{stamp}_{k}.mp4"
            k += 1
        self.btn_export.setEnabled(False)
        self.btn_open_result.setVisible(False)
        self.btn_open_folder.setVisible(False)
        self.export_progress.setVisible(True)
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(0)
        self.export_status.setText("开始生成，画面和音乐都在本机处理，不会上传到网上。")
        w = ExportWorker(self.project_path, out, self.choices["sub_style"],
                         self.choices["voice_mode"], self.choices["ratio"],
                         parent=self)
        self._export_worker = w
        w.progress.connect(self._on_export_progress)
        w.done.connect(self._on_export_done)
        w.start()

    def _on_export_progress(self, cur, total, msg):
        self.export_progress.setRange(0, total)
        self.export_progress.setValue(cur)
        self.export_status.setText(msg)

    def _on_export_done(self, res):
        self.export_progress.setVisible(False)
        self.btn_export.setEnabled(True)
        if not res.get("ok"):
            self.export_status.setText("没做成：" + res.get("error", "未知原因"))
            return
        v = res.get("verify", {})
        sec = v.get("duration_ms", 0) / 1000.0
        note = res.get("note") or ""
        p = str(res["path"])
        self.export_status.setText(
            f"做好了：{Path(p).name} · {v.get('width')}x{v.get('height')} · 约 {sec:.1f} 秒\n"
            f"存在：{p}" + (f"\n提醒：{note}" if note else ""))
        self._last_result = p
        self.btn_open_result.setVisible(True)
        self.btn_open_folder.setVisible(True)
        self._export_worker = None
        self._mark_done(4)

    def _open_result(self):
        p = getattr(self, "_last_result", "")
        if p and Path(p).exists():
            os.startfile(p)

    def _open_result_folder(self):
        p = getattr(self, "_last_result", "")
        if p and Path(p).exists():
            os.startfile(str(Path(p).parent))
