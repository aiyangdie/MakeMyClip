# -*- coding: utf-8 -*-
"""阶段 B · 工作台外壳（三页容器 + 顶栏导航）

本阶段范围（任务书阶段 B）：
  页面一 素材工作台  → 真实数据接入（本文件挂载 page_workspace）
  页面二 剪辑方案    → 占位（阶段 C 实现）
  页面三 预览与导出  → 占位（阶段 D 实现）

诚实要求：顶栏常驻"当前 AI 能力"标识，明确写出"基础算法测量，非 AI 理解"，
避免用户误以为系统已经看懂商品。
"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                               QLabel, QPushButton, QStackedWidget, QFrame,
                               QSizePolicy, QComboBox, QMessageBox, QFileDialog)

from ... import config
from .. import design_tokens as dt
from ...workshop_data import bridge
from ...workshop_data import models as M
from .page_workspace import WorkspacePage


# ============================================================================
# 顶栏
# ============================================================================
class TopBar(QFrame):
    """品牌 + 三页导航 + AI 能力标识 + 主题切换。"""

    page_changed = Signal(int)
    theme_toggled = Signal()

    STEPS = ["素材工作台", "剪辑方案", "预览与导出"]

    def __init__(self, dark=False, parent=None):
        super().__init__(parent)
        self._dark = dark
        self._current = 0
        self.setFixedHeight(56)
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(14)

        # 品牌
        mark = QLabel("M")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(26, 26)
        self._mark = mark
        name = QLabel("MakeMyClip")
        self._name = name
        lay.addWidget(mark)
        lay.addWidget(name)

        # 三页导航
        self.nav_btns = []
        nav = QFrame()
        self._nav_frame = nav
        nav_lay = QHBoxLayout(nav)
        nav_lay.setContentsMargins(3, 3, 3, 3)
        nav_lay.setSpacing(2)
        for i, s in enumerate(self.STEPS):
            b = QPushButton(f"{i + 1}  {s}")
            b.setCursor(Qt.PointingHandCursor)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, idx=i: self._on_nav(idx))
            nav_lay.addWidget(b)
            self.nav_btns.append(b)
        lay.addWidget(nav)

        lay.addStretch(1)

        # AI 能力标识（诚实告知，常驻）
        self.ai_badge = QLabel("当前：基础算法测量（非 AI 理解）")
        self.ai_badge.setToolTip(
            "系统目前只用 OpenCV 做画面变化/亮度/清晰度测量，\n"
            "没有接入视觉或语言模型，无法理解商品动作语义。\n"
            "识别引擎尚未通过正式集成验收。")
        lay.addWidget(self.ai_badge)

        # 主题
        self.theme_btn = QPushButton("◐")
        self.theme_btn.setFixedSize(30, 30)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setToolTip("切换亮色 / 暗色")
        self.theme_btn.clicked.connect(self.theme_toggled.emit)
        lay.addWidget(self.theme_btn)

        self.set_current(0)

    def _on_nav(self, idx):
        self.set_current(idx)
        self.page_changed.emit(idx)

    def set_current(self, idx):
        self._current = idx
        for i, b in enumerate(self.nav_btns):
            b.setChecked(i == idx)
        self.refresh()

    def set_ai_text(self, text, tone="warning"):
        self.ai_badge.setText(text)
        self._ai_tone = tone
        self.refresh()

    def set_dark(self, dark):
        self._dark = dark
        self.refresh()

    def refresh(self):
        t = dt.tokens(self._dark)
        self.setStyleSheet(f"QFrame{{background-color:{t['surface']};"
                          f"border-bottom:1px solid {t['border']};}}")
        self._mark.setStyleSheet(
            f"background-color:{t['primary']};color:{t['primary_text']};"
            f"border-radius:{dt.R_MD}px;font-weight:700;font-size:13px;")
        self._name.setStyleSheet(
            f"font-size:{dt.FS_BIG}px;font-weight:600;color:{t['text']};background:transparent;")
        self._nav_frame.setStyleSheet(
            f"QFrame{{background-color:{t['surface_2']};border-radius:{dt.R_LG}px;}}")
        for i, b in enumerate(self.nav_btns):
            if i == self._current:
                b.setStyleSheet(
                    f"QPushButton{{background-color:{t['surface']};color:{t['text']};"
                    f"border:1px solid {t['border']};border-radius:{dt.R_MD}px;"
                    f"padding:6px 12px;font-size:{dt.FS_BODY}px;font-weight:600;}}")
            else:
                b.setStyleSheet(
                    f"QPushButton{{background:transparent;color:{t['muted']};border:none;"
                    f"border-radius:{dt.R_MD}px;padding:6px 12px;font-size:{dt.FS_BODY}px;}}"
                    f"QPushButton:hover{{background-color:{t['surface']};color:{t['text']};}}")
        tone = getattr(self, "_ai_tone", "warning")
        bg = t["warning_bg"] if tone == "warning" else t["info_bg"]
        fg = t["warning"] if tone == "warning" else t["primary"]
        bd = t["warning"] if tone == "warning" else t["info_border"]
        self.ai_badge.setStyleSheet(
            f"QLabel{{background-color:{bg};color:{fg};border:1px solid {bd};"
            f"border-radius:{dt.R_PILL}px;padding:4px 12px;font-size:{dt.FS_HINT}px;}}")
        self.theme_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{t['muted']};border:none;"
            f"border-radius:{dt.R_MD}px;font-size:15px;}}"
            f"QPushButton:hover{{background-color:{t['surface_2']};color:{t['text']};}}")


# ============================================================================
# 占位页（阶段 C / D 才实现）
# ============================================================================
class PlaceholderPage(QWidget):
    """明确告诉用户"这页还没做"，不假装能用。"""

    def __init__(self, title, phase_note, will_have, dark=False, parent=None):
        super().__init__(parent)
        self._dark = dark
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.setSpacing(12)
        lay.addStretch(1)

        self.t = QLabel(title)
        self.t.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.t)

        self.n = QLabel(phase_note)
        self.n.setAlignment(Qt.AlignCenter)
        self.n.setWordWrap(True)
        lay.addWidget(self.n)

        self.w = QLabel(will_have)
        self.w.setAlignment(Qt.AlignCenter)
        self.w.setWordWrap(True)
        lay.addWidget(self.w)
        lay.addStretch(1)
        self.refresh()

    def set_dark(self, dark):
        self._dark = dark
        self.refresh()

    def refresh(self):
        t = dt.tokens(self._dark)
        self.t.setStyleSheet(f"font-size:{dt.FS_TITLE}px;font-weight:600;color:{t['text']};")
        self.n.setStyleSheet(f"font-size:{dt.FS_BODY}px;color:{t['warning']};")
        self.w.setStyleSheet(f"font-size:{dt.FS_HINT}px;color:{t['muted']};line-height:1.6;")


# ============================================================================
# 主窗口
# ============================================================================
class WorkspaceWindow(QMainWindow):
    """三页工作台。旧入口 main.py / main_wizard.py 完全不受影响。"""

    def __init__(self, db_path=None):
        super().__init__()
        self._dark = False
        self.db = None
        self.db_path = None
        self.project = None

        self.setWindowTitle(f"{config.APP_NAME} 工作台 · 素材与商品信息")
        self.resize(1280, 820)
        self.setMinimumSize(1024, 680)

        self._build_ui()
        self.apply_theme()
        if db_path:
            self.open_project(db_path)

    # ---------------- 界面 ----------------
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.topbar = TopBar(self._dark)
        self.topbar.page_changed.connect(self._goto_page)
        self.topbar.theme_toggled.connect(self._toggle_theme)
        root.addWidget(self.topbar)

        self.stack = QStackedWidget()
        self.page_workspace = WorkspacePage(self._dark)
        self.page_workspace.request_open_storyboard.connect(lambda: self._goto_page(1))
        self.page_workspace.status_message.connect(self._on_status)

        self.page_storyboard = PlaceholderPage(
            "剪辑方案（实验壳 · 未接通）",
            "请改用「完整工作台」或「五步向导」",
            "本三页工作台目前只有「素材」页接真实项目库。\n"
            "剪辑时间轴 / 换镜 / 锁定请打开：python main.py\n"
            "新手出片请打开：python main_wizard.py\n"
            "避免三套入口并行造成「点了没反应」的误解。",
            self._dark)
        self.page_preview = PlaceholderPage(
            "预览与导出（实验壳 · 未接通）",
            "请改用「完整工作台 → 导出」或向导第 5 步",
            "真实导出链在 main.py / main_wizard.py 的 ExportWorker 与 final_exporter。\n"
            "本页仅为骨架占位，不会写出成片。",
            self._dark)

        for p in (self.page_workspace, self.page_storyboard, self.page_preview):
            self.stack.addWidget(p)
        root.addWidget(self.stack, 1)

        self.setCentralWidget(central)
        self.statusBar().showMessage("就绪 — 请先新建或打开项目")

    # ---------------- 页面 ----------------
    def _goto_page(self, idx):
        if idx == 1 and not self.project:
            QMessageBox.information(self, "还没有打开项目",
                                    "请先在「素材工作台」打开或新建项目，再进入剪辑方案。")
            self.topbar.set_current(0)
            return
        if idx in (1, 2):
            # 阶段 B：这两页还没实现，如实告知而不是给个假界面
            QMessageBox.information(
                self, "本阶段暂未实现",
                f"「{TopBar.STEPS[idx]}」将在"
                f"{'阶段 C' if idx == 1 else '阶段 D'}实现。\n\n"
                "阶段 B 只做素材工作台，避免交付半成品界面。")
            self.topbar.set_current(0)
            return
        self.stack.setCurrentIndex(idx)
        self.setWindowTitle(f"{config.APP_NAME} 工作台 · {TopBar.STEPS[idx]}")

    # ---------------- 主题 ----------------
    def _toggle_theme(self):
        self._dark = not self._dark
        self.apply_theme()

    def apply_theme(self):
        self.setStyleSheet(dt.qss(self._dark))
        t = dt.tokens(self._dark)
        self.topbar.set_dark(self._dark)
        self.page_workspace.set_dark(self._dark)
        self.page_storyboard.set_dark(self._dark)
        self.page_preview.set_dark(self._dark)
        self.statusBar().setStyleSheet(
            f"QStatusBar{{background-color:{t['surface']};color:{t['muted']};"
            f"border-top:1px solid {t['border']};}}")

    # ---------------- 项目 ----------------
    def open_project(self, db_path):
        from ...db import ProjectDB
        try:
            db = ProjectDB(db_path)
            project = bridge.load_project(db, db_path)
        except Exception as e:  # noqa: BLE001 - 打开失败要如实报，不静默
            QMessageBox.critical(self, "打开项目失败",
                                 f"无法读取项目数据库：\n{db_path}\n\n{type(e).__name__}: {e}")
            return False
        self.db = db
        self.db_path = str(db_path)
        self.project = project
        self.page_workspace.bind_project(db, project)
        # 顶栏 AI 标识按真实能力刷新
        cap = bridge.ai_capability_summary(db)
        if not cap["has_vlm"] and not cap["has_cloud"]:
            self.topbar.set_ai_text("当前：基础算法测量（非 AI 理解）", "warning")
        self.statusBar().showMessage(
            f"已打开：{project.name} · {len(project.assets)} 条素材")
        return True

    def _on_status(self, msg):
        self.statusBar().showMessage(msg)
