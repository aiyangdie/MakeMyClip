import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from app.ui.main_window import MainWindow
from app import db as dbmod, config

app = QApplication(sys.argv)
w = MainWindow()
w.db = dbmod.ProjectDB(str(config.DB_DIR / "_stage4_e2e.db"))
w.project_path = str(config.DB_DIR / "_stage4_e2e.db")
w.nav.setCurrentRow(5); w.refresh_timeline()
print("时间线镜头数 =", w.shot_list.count())
print("首镜头 =", w.shot_list.item(0).text())
# 选中一个镜头看编辑区
w.shot_list.setCurrentRow(0); w._shot_selected(w.shot_list.item(0))
print("编辑区可见 =", w.shot_edit.isVisible(), "| 起始 =", w.shot_start.text(), "| 结束 =", w.shot_end.text())
print("镜头信息 =", w.shot_info.text().replace("\n", " "))
w.render_result.setPlainText("镜头处理：新生成 4，缓存复用 0\n成片：exports\\_stage4_test_final.mp4\n校验：720x1280 30fps 12.0s 可解码=True")
w.grab().save("tests/gui_stage4_timeline.png")
print("截图已保存")
QTimer.singleShot(200, app.quit)
sys.exit(app.exec())
