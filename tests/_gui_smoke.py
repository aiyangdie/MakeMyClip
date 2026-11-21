import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
w = MainWindow()
w.show()
print("GUI_OK: 窗口标题 =", w.windowTitle())
print("GUI_OK: 页面数 =", w.stack.count())
pix = w.grab()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_smoke.png")
pix.save(out)
print("GUI_OK: 截图已保存", out)
QTimer.singleShot(300, app.quit)
sys.exit(app.exec())
