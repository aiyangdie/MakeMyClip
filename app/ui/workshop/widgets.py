# -*- coding: utf-8 -*-
"""阶段 B · 工作台通用组件

设计约束：
  - 只用 design_tokens 的语义色（tokens/inline/qss），界面里不写死 hex。
  - 组件只负责"显示"，不读数据库、不做业务判断（判断在 workshop_data）。
  - 缩略图缺失/损坏时显示占位，不崩、不空白。
"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QFont, QPainter, QColor
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
                               QSizePolicy, QPushButton)

from .. import design_tokens as dt


# ============================================================================
# 状态胶囊
# ============================================================================
class StatusChip(QLabel):
    """五态胶囊：未分析/分析中/已基础测量/待人工确认/分析失败。"""

    TONE_MAP = {
        "muted": ("disabled_bg", "muted"),
        "info": ("info_bg", "primary"),
        "success": ("success_bg", "success"),
        "warning": ("warning_bg", "warning"),
        "danger": ("danger_bg", "danger"),
    }

    def __init__(self, text="", tone="muted", dark=False, parent=None):
        super().__init__(text, parent)
        self._tone = tone
        self._dark = dark
        self.setAlignment(Qt.AlignCenter)
        self._apply()

    def set_status(self, text, tone):
        self.setText(text)
        self._tone = tone
        self._apply()

    def set_dark(self, dark):
        self._dark = dark
        self._apply()

    def _apply(self):
        t = dt.tokens(self._dark)
        bg_key, fg_key = self.TONE_MAP.get(self._tone, ("disabled_bg", "muted"))
        self.setStyleSheet(
            f"QLabel{{background-color:{t[bg_key]};color:{t[fg_key]};"
            f"border-radius:{dt.R_SM}px;padding:2px 8px;"
            f"font-size:{dt.FS_HINT}px;font-weight:500;}}")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


class TinyTag(QLabel):
    """小标签（图片/视频、锁定、待确认 N 等）。"""

    def __init__(self, text="", tone="muted", dark=False, parent=None):
        super().__init__(text, parent)
        self._tone = tone
        self._dark = dark
        self.setAlignment(Qt.AlignCenter)
        self.refresh()

    def set_text(self, text, tone=None):
        self.setText(text)
        if tone:
            self._tone = tone
        self.refresh()

    def set_dark(self, dark):
        self._dark = dark
        self.refresh()

    def refresh(self):
        t = dt.tokens(self._dark)
        bg, fg = StatusChip.TONE_MAP.get(self._tone, ("disabled_bg", "muted"))
        self.setStyleSheet(
            f"QLabel{{background-color:{t[bg]};color:{t[fg]};"
            f"border-radius:{dt.R_SM}px;padding:1px 6px;"
            f"font-size:{dt.FS_HINT - 1}px;}}")


# ============================================================================
# 可点击卡片
# ============================================================================
class ClickFrame(QFrame):
    """整块可点击的卡片（鼠标左键）。"""
    clicked = Signal()
    double_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


# ============================================================================
# 缩略图
# ============================================================================
class Thumb(QLabel):
    """3:4 缩略图；缺失/损坏时显示占位文字，不崩。"""

    def __init__(self, w=132, h=176, dark=False, parent=None):
        super().__init__(parent)
        self._w, self._h = w, h
        self._dark = dark
        self.setFixedSize(w, h)
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)
        self.show_placeholder("无缩略图")

    def show_placeholder(self, text="无缩略图"):
        t = dt.tokens(self._dark)
        self.setPixmap(QPixmap())          # 清掉旧图
        self.setText(text)
        self.setStyleSheet(
            f"QLabel{{background-color:{t['surface_2']};color:{t['hint']};"
            f"border:1px solid {t['border']};border-radius:{dt.R_SM}px;"
            f"font-size:{dt.FS_HINT - 1}px;}}")

    def load(self, path):
        p = str(path or "").strip()
        if not p or not Path(p).exists():
            self.show_placeholder("无缩略图")
            return False
        pm = QPixmap(p)
        if pm.isNull():
            self.show_placeholder("缩略图损坏")
            return False
        scaled = pm.scaled(self._w, self._h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setText("")
        self.setStyleSheet(f"QLabel{{border:1px solid {dt.tokens(self._dark)['border']};"
                          f"border-radius:{dt.R_SM}px;background:transparent;}}")
        self.setPixmap(scaled)
        return True


# ============================================================================
# 素材卡
# ============================================================================
class AssetCard(ClickFrame):
    """一条素材。显示：缩略图 / 文件名 / 类型 / 时长 / 尺寸 / 五态 / 待确认数。"""

    CARD_W = 176

    def __init__(self, vm, dark=False, parent=None):
        super().__init__(parent)
        self.vm = vm
        self._dark = dark
        self.setFixedWidth(self.CARD_W)
        self.setObjectName("card")
        self._build()
        self.apply_theme(dark)

    def _build(self):
        v = self.vm
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # 缩略图区（左上角叠状态胶囊）
        thumb_wrap = QWidget()
        thumb_wrap.setFixedHeight(140)
        tw = QVBoxLayout(thumb_wrap)
        tw.setContentsMargins(0, 0, 0, 0)
        tw.setSpacing(0)

        self.thumb = Thumb(140, 140, self._dark)
        # 图片/视频用不同底，但不依赖内容
        if not v.thumb_path:
            self.thumb.show_placeholder("图片" if v.is_image else "无缩略图")
        else:
            if not self.thumb.load(v.thumb_path):
                self.thumb.show_placeholder("缩略图损坏")
        tw.addWidget(self.thumb, 0, Qt.AlignHCenter)

        root.addWidget(thumb_wrap)

        # 状态行
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        self.chip = StatusChip(v.status_label, v.status_tone, self._dark)
        row1.addWidget(self.chip)
        self.kind_tag = TinyTag(v.kind_text, "muted", self._dark)
        row1.addWidget(self.kind_tag)
        if v.pending_count:
            self.pend_tag = TinyTag(f"待确认 {v.pending_count}", "warning", self._dark)
            row1.addWidget(self.pend_tag)
        else:
            self.pend_tag = None
        row1.addStretch()
        root.addLayout(row1)

        # 文件名（两行省略）
        self.name_lab = QLabel(v.filename)
        self.name_lab.setWordWrap(True)
        self.name_lab.setFixedHeight(34)
        self.name_lab.setToolTip(v.path)
        root.addWidget(self.name_lab)

        # 时长 · 尺寸
        meta = f"{v.duration_text} · {v.size_text}"
        self.meta_lab = QLabel(meta)
        root.addWidget(self.meta_lab)

        # 说明（诚实提示）
        if v.note:
            self.note_lab = QLabel(v.note)
            self.note_lab.setWordWrap(True)
            self.note_lab.setFixedHeight(30)
            root.addWidget(self.note_lab)
        else:
            self.note_lab = None

        root.addStretch()

    def apply_theme(self, dark):
        self._dark = dark
        t = dt.tokens(dark)
        self.setStyleSheet(dt.inline("card", dark))
        self.chip.set_dark(dark)
        self.kind_tag.set_dark(dark)
        if self.pend_tag:
            self.pend_tag.set_dark(dark)
        self.name_lab.setStyleSheet(f"font-size:{dt.FS_BODY}px;color:{t['text']};")
        self.meta_lab.setStyleSheet(f"font-size:{dt.FS_HINT}px;color:{t['muted']};")
        if self.note_lab:
            tone = "danger" if self.vm.status == "failed" else "warning" \
                if self.vm.status == "confirm" else "hint"
            self.note_lab.setStyleSheet(dt.inline(tone, dark))


# ============================================================================
# 统计小条
# ============================================================================
class StatChip(QFrame):
    """顶部统计：数字 + 说明。可点击时带 hover。"""

    clicked = Signal()

    def __init__(self, value=0, label="", tone="muted", clickable=False, dark=False, parent=None):
        super().__init__(parent)
        self._dark = dark
        self._tone = tone
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(6)
        self.num = QLabel(str(value))
        self.lab = QLabel(label)
        lay.addWidget(self.num)
        lay.addWidget(self.lab)
        self.refresh()

    def set_value(self, value, label=None):
        self.num.setText(str(value))
        if label is not None:
            self.lab.setText(label)

    def set_dark(self, dark):
        self._dark = dark
        self.refresh()

    def refresh(self):
        t = dt.tokens(self._dark)
        if self._tone == "warning":
            bg, fg, bd = t["warning_bg"], t["warning"], t["warning"]
        elif self._tone == "danger":
            bg, fg, bd = t["danger_bg"], t["danger"], t["danger"]
        elif self._tone == "success":
            bg, fg, bd = t["success_bg"], t["success"], t["border"]
        else:
            bg, fg, bd = t["surface"], t["muted"], t["border"]
        self.setStyleSheet(f"QFrame{{background-color:{bg};border:1px solid {bd};"
                          f"border-radius:{dt.R_MD}px;}}")
        self.num.setStyleSheet(f"font-size:{dt.FS_BIG}px;font-weight:600;color:{t['text']};")
        self.lab.setStyleSheet(f"font-size:{dt.FS_HINT}px;color:{fg};")

    def mousePressEvent(self, event):
        if self._clickable and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ============================================================================
# 空态
# ============================================================================
class EmptyState(QFrame):
    """空态：图标 + 标题 + 说明 + 主按钮。"""

    action = Signal()

    def __init__(self, title="这里还没有素材", detail="", button_text="",
                 dark=False, parent=None):
        super().__init__(parent)
        self._dark = dark
        self.setObjectName("drop")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 34, 28, 34)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignCenter)

        self.icon = QLabel("📁")
        self.icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.icon)

        self.title = QLabel(title)
        self.title.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.title)

        self.detail = QLabel(detail)
        self.detail.setAlignment(Qt.AlignCenter)
        self.detail.setWordWrap(True)
        lay.addWidget(self.detail)

        self.btn = None
        if button_text:
            self.btn = QPushButton(button_text)
            self.btn.setObjectName("primary")
            self.btn.setCursor(Qt.PointingHandCursor)
            self.btn.clicked.connect(self.action.emit)
            lay.addWidget(self.btn, 0, Qt.AlignCenter)

        self.refresh()

    def refresh(self):
        t = dt.tokens(self._dark)
        self.setStyleSheet(dt.inline("drop", self._dark))
        self.icon.setStyleSheet(f"font-size:30px;color:{t['muted']};background:transparent;")
        self.title.setStyleSheet(f"font-size:{dt.FS_BIG}px;font-weight:600;color:{t['text']};"
                                "background:transparent;")
        self.detail.setStyleSheet(f"font-size:{dt.FS_HINT}px;color:{t['muted']};"
                                 "background:transparent;")


# ============================================================================
# 分组行
# ============================================================================
class GroupRow(ClickFrame):
    """左侧分组列表的一行。"""

    def __init__(self, name, count, active=False, dark=False, parent=None):
        super().__init__(parent)
        self._name = name
        self._count = count
        self._active = active
        self._dark = dark
        self.setFixedHeight(34)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(6)
        self.name_lab = QLabel(name)
        self.name_lab.setStyleSheet(f"font-size:{dt.FS_BODY}px;background:transparent;")
        self.count_lab = QLabel(str(count))
        self.count_lab.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.name_lab, 1)
        lay.addWidget(self.count_lab)
        self.refresh(active, dark)

    @property
    def group_name(self):
        return self._name

    def refresh(self, active=None, dark=None):
        if active is not None:
            self._active = active
        if dark is not None:
            self._dark = dark
        t = dt.tokens(self._dark)
        if self._active:
            self.setStyleSheet(
                f"QFrame{{background-color:{t['sel_bg']};border:1px solid {t['sel_border']};"
                f"border-radius:{dt.R_SM}px;}}")
            self.name_lab.setStyleSheet(
                f"font-size:{dt.FS_BODY}px;color:{t['primary']};font-weight:600;"
                "background:transparent;")
            self.count_lab.setStyleSheet(
                f"font-size:{dt.FS_HINT}px;color:{t['primary']};background:transparent;")
        else:
            self.setStyleSheet("QFrame{background:transparent;border:none;}")
            self.name_lab.setStyleSheet(
                f"font-size:{dt.FS_BODY}px;color:{t['muted']};background:transparent;")
            self.count_lab.setStyleSheet(
                f"font-size:{dt.FS_HINT}px;color:{t['hint']};background:transparent;")
