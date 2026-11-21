import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from app.ui.main_window import MainWindow
from app import db as dbmod

app = QApplication(sys.argv)
w = MainWindow()
proj = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects", "_stage3_e2e.db")
w.db = dbmod.ProjectDB(proj)
w.project_path = proj
# 载入匹配结果到内存，模拟已匹配
w.match_results = w.db.get_match_results()
# 分析页
w.nav.setCurrentRow(2); w.refresh_analysis()
print("分析页表格行数 =", w.clip_table.rowCount(), "列数 =", w.clip_table.columnCount())
# 选中第一行看识别明细
w.clip_table.selectRow(0); w._clip_selected(w.clip_table.model().index(0,0))
print("识别明细字数 =", len(w.clip_detail.toPlainText()))
w.grab().save("tests/gui_stage3_analysis.png")
# 分镜页
w.nav.setCurrentRow(4); w.refresh_storyboards()
print("分镜列表行数 =", w.story_list.count())
print("分镜列表首行 =", w.story_list.item(0).text())
# 选中第一个分镜看候选
w._story_selected(w.story_list.item(0))
print("候选列表项数 =", w.cand_list.count())
print("候选理由 =", w.cand_reason.toPlainText()[:80])
w.grab().save("tests/gui_stage3_storyboard.png")
print("截图已保存")
QTimer.singleShot(200, app.quit)
sys.exit(app.exec())
