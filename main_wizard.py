# -*- coding: utf-8 -*-
"""阶段十一新入口：向导式界面（新增文件）。

旧入口 main.py 原样保留，随时可以把桌面启动器改回去，一键回退。
"""
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from app.ui.wizard import WizardWindow


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = WizardWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
