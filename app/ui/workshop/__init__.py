# -*- coding: utf-8 -*-
"""阶段 B · 三页工作台（新入口 app/ui/workshop/）

与旧界面的关系：
  - 本包**不 import** app.ui.wizard / app.ui.main_window。
  - 旧入口 main.py（8 页工作台）与 main_wizard.py（5 步向导）完全不受影响。
  - 新入口 main_workspace.py 独立启动；出问题只需改桌面快捷方式一行即可回退。
"""
from .shell import WorkspaceWindow, TopBar, PlaceholderPage  # noqa: F401
from .page_workspace import WorkspacePage  # noqa: F401

__all__ = ["WorkspaceWindow", "TopBar", "PlaceholderPage", "WorkspacePage"]
