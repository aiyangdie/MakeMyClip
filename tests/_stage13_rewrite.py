# -*- coding: utf-8 -*-
"""阶段十三：按分段替换重做 wizard.py 界面骨架。

从 class ExportWorker 到文件末尾的「出片 / 数据 / 交互」逻辑字节级保留，
只替换：模块头、辅助部件类、WizardWindow 的 __init__ 与 5 个页面构建方法，
以及逻辑段里 6 处动态卡片的硬编码取色（改为走 design_tokens）。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "app/ui/wizard.py"
text = SRC.read_text(encoding="utf-8")


def cut(start_marker, end_marker):
    """返回 (前缀, 命中段, 后缀)，命中段含 start_marker 不含 end_marker。"""
    a = text.index(start_marker)
    b = text.index(end_marker, a)
    return text[:a], text[a:b], text[b:]


# ---------------------------------------------------------------- 新模块头
NEW_HEAD = '''# -*- coding: utf-8 -*-
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


'''

# ------------------------------------------------- 辅助部件类（ClickFrame 保留）
NEW_WIDGETS = '''class ClickFrame(QFrame):
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
        md.setText("\\n".join(it.text() for it in items))
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
        sub = _label("比如桌面上那个「素材」文件夹，整个拖进来就行\\n"
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


'''

# ---------------------------------------------------- WizardWindow 头 + 界面骨架
NEW_WINDOW_HEAD = '''class WizardWindow(QMainWindow):
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

'''

# ---------------------------------------------------------------- 执行替换
# 1) 模块头：开头 -> def _video_files
_, _, tail = cut("# -*- coding: utf-8 -*-", "def _video_files(")
text = NEW_HEAD + tail

# 2) _video_files / _friendly_error 原样保留，替换 ClickFrame -> class ExportWorker
pre, _, post = cut("class ClickFrame(QFrame):", "class ExportWorker(QThread):")
text = pre + NEW_WIDGETS + post

# 3) WizardWindow 头 + 界面骨架：class WizardWindow -> 数据段注释
pre, _, post = cut("class WizardWindow(QMainWindow):", "    # ---------------- 数据 ----------------")
text = pre + NEW_WINDOW_HEAD + post

# 4) 逻辑段里 6 处动态卡片取色：改为走主题（其余逻辑一字不动）
subs = [
    ('card.setStyleSheet(_CARD_MISS if missing else _CARD)',
     'card.setStyleSheet(self._style("card_miss" if missing else "card"))'),
    ('pic.setStyleSheet("color:#854F0B;font-size:12px;background:#F5DFC0;")',
     'pic.setStyleSheet(self._style("missing_pic"))'),
    ('pic.setStyleSheet("color:#888780;font-size:12px;")',
     'pic.setStyleSheet(self._style("loading_pic"))'),
    ('name.setStyleSheet(\n                "font-size:12px;color:#854F0B;" if missing else "font-size:12px;color:#2C2C2A;")',
     'name.setStyleSheet(self._style("shot_name_miss" if missing else "shot_name"))'),
    ('sub.setStyleSheet("font-size:11px;color:#5F5E5A;")',
     'sub.setStyleSheet(self._style("shot_sub"))'),
    ('card.setStyleSheet(_CARD_ON if key == self.choices["sub_style"] else _CARD)',
     'card.setStyleSheet(self._style("card_on" if key == self.choices["sub_style"] else "card"))'),
]
for old, new in subs:
    assert text.count(old) == 1, f"替换锚点不唯一或不存在: {old[:60]!r} count={text.count(old)}"
    text = text.replace(old, new)

SRC.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------- 自检
hexes = re.findall(r"#[0-9a-fA-F]{6}", text)
print("WIZARD_HEX_LEFT =", hexes)
for name in ("STEPS", "STEP_HINTS", "MIME_ASSETS", "_friendly_error", "_video_files",
             "class DropArea", "class ExportWorker", "class WizardWindow",
             "while out.exists():", "wizard_lines", "self._toggle_theme",
             "self.label_table", "self.shot_grid", "self.asset_list",
             "self.btn_select_all", "self.btn_remove", "self.last_step",
             "self.status_label", "self.stepbar", "self.more_box",
             "self.btn_export", "self.export_status", "self.summary"):
    assert name in text, f"缺失必要名字: {name}"
for forbidden in ("_CARD_ON", "_CARD_MISS", "_BIG_BTN", "_BTN_CURRENT"):
    assert forbidden not in text, f"旧硬编码样式常量仍被引用: {forbidden}"
print("REWRITE_OK lines =", len(text.splitlines()))
