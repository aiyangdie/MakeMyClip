# -*- coding: utf-8 -*-
"""MakeMyClip 工作台入口（阶段 B 新增）

三页工作台：素材与商品信息 / 剪辑方案 / 预览与导出。

与旧入口的关系（重要）：
  main.py            → 8 页完整工作台（备用，未改动）
  main_wizard.py     → 5 步向导（当前桌面默认，未改动）
  main_workspace.py  → 本文件，三页工作台（新增）

回退方式：桌面快捷方式改回 main_wizard.py 即可，一行搞定。
"""
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase

from app.ui.workshop import WorkspaceWindow


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 中文字体（与旧入口保持一致）
    for fp in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
        import os
        if os.path.exists(fp):
            QFontDatabase.addApplicationFont(fp)
    app.setFont(QFont("Microsoft YaHei", 10))

    # 命令行可传项目路径：python main_workspace.py projects/xxx.db
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    win = WorkspaceWindow(db_path=db_path)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
