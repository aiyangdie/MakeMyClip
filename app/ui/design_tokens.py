# -*- coding: utf-8 -*-
"""阶段十三 · 统一设计主题（零第三方依赖）。

设计规矩的出处（只借公开设计语言，不复制任何代码、不引入任何库）：
  - Google Material Design 3 Design Kit —— Apache 2.0，免费、商用允许
        https://m3.material.io/  /  https://www.figma.com/community
  - shadcn/ui 语义化 token 体系 —— MIT
        https://ui.shadcn.com/
  - Figma Community 免费设计文件通用许可 —— CC BY 4.0（署名即可商用）
        https://www.figma.com/community

我们只采用其中三条公开的、不涉及代码的规矩：
  1. 语义命名：颜色叫「背景 / 卡片 / 正文 / 次要文字 / 边框 / 主按钮 / 提醒」，
     不叫「蓝色 / 米色」。换主题只改这一张表，界面里不散落色值。
  2. 中性基底 + 一个强调色：彩色只出现在主按钮、选中态和状态提醒上。
  3. 1px 细边框分层 + 圆角单源派生 + 低对比次级文字，不靠花哨阴影。

所有色值是本项目按 Windows 桌面软件自定的，未从任何设计文件里取数；
本文件是界面唯一允许出现色值的地方，wizard.py 里不再写死 hex。
"""

# 单一圆角源，其余全部派生（shadcn/ui 的做法）
RADIUS = 10
R_SM = max(4, int(RADIUS * 0.6))
R_MD = int(RADIUS * 0.8)
R_LG = RADIUS
R_XL = int(RADIUS * 1.4)
R_PILL = 999

# 字号（桌面软件，最小 12px，比旧版 11px 更好读）
FS_BODY = 13
FS_TITLE = 16
FS_HINT = 12
FS_BIG = 15

LIGHT = {
    "bg": "#F7F8FA",          # 页面底
    "surface": "#FFFFFF",     # 卡片
    "surface_2": "#F1F3F6",   # 次级表面 / 指标块
    "text": "#1B1F24",        # 正文
    "muted": "#5C6470",       # 次级文字
    "hint": "#7B8490",        # 提示
    "border": "#DEE2E8",      # 1px 边框
    "primary": "#2F6BEF",     # 主按钮
    "primary_hover": "#2258D6",
    "primary_text": "#FFFFFF",
    "on_primary": "#FFFFFF",
    "success": "#1D9E75",
    "success_bg": "#E6F6F0",
    "warning": "#A8680F",
    "warning_bg": "#FFF3E0",
    "danger": "#C0392B",
    "danger_bg": "#FDEDEC",
    "info_bg": "#ECF2FF",
    "info_border": "#C7D9FF",
    "disabled": "#B9C0C9",
    "disabled_bg": "#E9ECF0",
    "sel_bg": "#E8F0FF",
    "sel_border": "#2F6BEF",
}

DARK = {
    "bg": "#14171C",
    "surface": "#1B1F26",
    "surface_2": "#232830",
    "text": "#E8EAED",
    "muted": "#9AA3AF",
    "hint": "#788290",
    "border": "#313844",
    "primary": "#5B8DFF",
    "primary_hover": "#74A0FF",
    "primary_text": "#0E1218",
    "on_primary": "#0E1218",
    "success": "#5DCAA5",
    "success_bg": "#143128",
    "warning": "#E5B567",
    "warning_bg": "#33291A",
    "danger": "#F09595",
    "danger_bg": "#3A1E1E",
    "info_bg": "#1B2739",
    "info_border": "#2E4A78",
    "disabled": "#5A636F",
    "disabled_bg": "#262C35",
    "sel_bg": "#1D3050",
    "sel_border": "#5B8DFF",
}


def tokens(dark=False):
    """取当前主题的一整套语义颜色。"""
    return DARK if dark else LIGHT


def qss(dark=False, radius=RADIUS):
    """生成全局 QSS：所有部件统一走语义 token，界面里不再写死色值。"""
    t = tokens(dark)
    return f"""
QWidget {{
    background-color: {t['bg']};
    color: {t['text']};
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: {FS_BODY}px;
}}
QMainWindow, QDialog {{ background-color: {t['bg']}; }}
QLabel {{ background: transparent; color: {t['text']}; }}
QFrame#card, QFrame#box, QFrame#drop {{
    background-color: {t['surface']};
    border: 1px solid {t['border']};
    border-radius: {R_XL}px;
}}
QFrame#subtle {{
    background-color: {t['surface_2']};
    border: none;
    border-radius: {R_LG}px;
}}
QFrame#warning {{
    background-color: {t['warning_bg']};
    border: 1px solid {t['warning']};
    border-radius: {R_LG}px;
}}
QFrame#box {{
    background-color: {t['info_bg']};
    border: 1px solid {t['info_border']};
}}
QLabel#step_title {{ font-size:{FS_TITLE}px; font-weight:500; color:{t['text']}; }}
QLabel#step_desc  {{ font-size:{FS_BODY}px; color:{t['muted']}; }}
QLabel#step_hint  {{ font-size:{FS_HINT}px; color:{t['hint']}; }}
QLabel#metric_num {{ font-size:22px; font-weight:500; color:{t['text']}; }}
QLabel#metric_label {{ font-size:{FS_HINT}px; color:{t['hint']}; }}
QLabel#drop_main {{ font-size:{FS_BIG}px; font-weight:500; color:{t['text']}; }}
QLabel#drop_sub  {{ font-size:{FS_HINT}px; color:{t['muted']}; }}
QLabel#cap {{ font-size:{FS_BODY}px; color:{t['muted']}; }}
QLabel#warning_text {{ font-size:{FS_HINT}px; color:{t['warning']}; }}
QLabel#success_text {{ font-size:{FS_BODY}px; color:{t['success']}; }}
QLabel#info_text {{ font-size:{FS_BODY}px; color:{t['primary']}; }}
QPushButton {{
    background-color: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: {R_MD}px;
    padding: 8px 14px;
    font-size: {FS_BODY}px;
}}
QPushButton:hover {{ background-color: {t['surface_2']}; border-color: {t['primary']}; }}
QPushButton:pressed {{ background-color: {t['sel_bg']}; }}
QPushButton:disabled {{
    background-color: {t['disabled_bg']};
    color: {t['disabled']};
    border-color: {t['border']};
}}
QPushButton#primary {{
    background-color: {t['primary']};
    color: {t['primary_text']};
    border: 1px solid {t['primary']};
    font-weight: 500;
    padding: 11px 24px;
    border-radius: {R_MD}px;
}}
QPushButton#primary:hover {{ background-color: {t['primary_hover']}; border-color: {t['primary_hover']}; }}
QPushButton#primary:disabled {{
    background-color: {t['disabled_bg']}; color: {t['disabled']}; border-color: {t['border']};
}}
QPushButton#ghost {{ background: transparent; border: none; color: {t['muted']}; padding: 6px 10px; }}
QPushButton#ghost:hover {{ color: {t['primary']}; background-color: {t['surface_2']}; }}
QPushButton#danger {{ color: {t['danger']}; }}
QPushButton#danger:hover {{ background-color: {t['danger_bg']}; border-color: {t['danger']}; }}
QPushButton#step_todo, QPushButton#step_done, QPushButton#step_current {{
    border-radius: 13px; padding: 0; font-size: {FS_HINT}px;
}}
QPushButton#step_todo {{
    background-color: {t['surface_2']}; color: {t['muted']};
    border: 1px solid {t['border']};
}}
QPushButton#step_done {{
    background-color: {t['success_bg']}; color: {t['success']};
    border: 1px solid {t['success']};
}}
QPushButton#step_current {{
    background-color: {t['primary']}; color: {t['primary_text']};
    border: 1px solid {t['primary']}; font-weight: 500;
}}
QListWidget, QTableWidget, QComboBox, QTextEdit, QLineEdit {{
    background-color: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: {R_LG}px;
    padding: 4px;
    selection-background-color: {t['sel_bg']};
    selection-color: {t['text']};
}}
QListWidget::item {{ padding: 7px 6px; border-radius: {R_SM}px; }}
QListWidget::item:selected {{
    background-color: {t['sel_bg']};
    border: 1px solid {t['sel_border']};
}}
QListWidget::item:hover {{ background-color: {t['surface_2']}; }}
QTableWidget {{ gridline-color: {t['border']}; }}
QTableWidget::item {{ padding: 6px 4px; }}
QHeaderView::section {{
    background-color: {t['surface_2']};
    color: {t['muted']};
    border: none;
    border-bottom: 1px solid {t['border']};
    padding: 8px 6px;
    font-size: {FS_HINT}px;
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {t['surface']}; color: {t['text']};
    border: 1px solid {t['border']}; selection-background-color: {t['sel_bg']};
}}
QProgressBar {{
    background-color: {t['surface_2']};
    border: none; border-radius: {R_SM}px; height: 10px; text-align: center;
}}
QProgressBar::chunk {{ background-color: {t['primary']}; border-radius: {R_SM}px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QMenu {{ background-color: {t['surface']}; color: {t['text']}; border: 1px solid {t['border']}; }}
QMenu::item:selected {{ background-color: {t['sel_bg']}; }}
QToolTip {{ background-color: {t['surface']}; color: {t['text']}; border: 1px solid {t['border']}; }}
"""


def inline(kind, dark=False, extra=""):
    """少数需要单独强调的部件，用语义名取色，不写死 hex。"""
    t = tokens(dark)
    base = {
        "title": f"font-size:{FS_TITLE}px;font-weight:500;color:{t['text']};",
        "headline": f"font-size:{FS_BIG}px;font-weight:500;color:{t['text']};",
        "body": f"font-size:{FS_BODY}px;color:{t['text']};",
        "muted": f"font-size:{FS_HINT}px;color:{t['muted']};",
        "hint": f"font-size:{FS_HINT}px;color:{t['hint']};",
        "success": f"font-size:{FS_BODY}px;color:{t['success']};",
        "warning": f"font-size:{FS_HINT}px;color:{t['warning']};",
        "danger": f"font-size:{FS_BODY}px;color:{t['danger']};",
        "card": (f"QFrame{{background-color:{t['surface']};"
                 f"border:1px solid {t['border']};border-radius:{R_XL}px;}}"),
        "card_on": (f"QFrame{{background-color:{t['sel_bg']};"
                    f"border:2px solid {t['sel_border']};border-radius:{R_XL}px;}}"),
        "card_miss": (f"QFrame{{background-color:{t['warning_bg']};"
                      f"border:2px solid {t['warning']};border-radius:{R_XL}px;}}"),
        "drop": (f"QFrame{{background-color:{t['info_bg']};"
                 f"border:2px dashed {t['info_border']};border-radius:{R_XL}px;}}"),
        "box": (f"QFrame{{background-color:{t['info_bg']};"
                f"border:1px solid {t['info_border']};border-radius:{R_XL}px;}}"),
        "warning_box": (f"QFrame{{background-color:{t['warning_bg']};"
                        f"border:1px solid {t['warning']};border-radius:{R_LG}px;}}"),
        "metric": (f"QFrame{{background-color:{t['surface_2']};"
                   f"border:none;border-radius:{R_LG}px;}}"),
        "metric_num": f"font-size:22px;font-weight:500;color:{t['text']};",
        "metric_label": f"font-size:{FS_HINT}px;color:{t['hint']};",
        "drop_main": f"font-size:{FS_BIG}px;font-weight:500;color:{t['text']};",
        "drop_sub": f"font-size:{FS_HINT}px;color:{t['muted']};",
        "missing_pic": (f"font-size:{FS_HINT}px;color:{t['warning']};"
                        f"background-color:{t['warning_bg']};"),
        "loading_pic": f"font-size:{FS_HINT}px;color:{t['hint']};",
        "shot_name": f"font-size:{FS_HINT}px;color:{t['text']};",
        "shot_name_miss": f"font-size:{FS_HINT}px;color:{t['warning']};",
        "shot_sub": f"font-size:{FS_HINT}px;color:{t['muted']};",
    }.get(kind, "")
    return base + extra


def set_object_name(widget, name):
    """给部件挂语义 objectName，QSS 才能只按用途上色。"""
    widget.setObjectName(name)
    return widget
