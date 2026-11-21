# -*- coding: utf-8 -*-
"""MakeMyClip 入口。"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from app.ui.main_window import MainWindow


def main():
    # 高分屏清晰显示
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from app import config as _cfg
    _cfg.STAGE = "第五阶段 · 文案·字幕·中文配音·音乐"
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
