import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from app.ui.main_window import MainWindow
from app import db as dbmod, config

app = QApplication(sys.argv)
w = MainWindow()
w.db = dbmod.ProjectDB(str(config.DB_DIR / "_stage5_e2e.db"))
w.project_path = str(config.DB_DIR / "_stage5_e2e.db")
w.nav.setCurrentRow(6)
w.refresh_audio_page()
print("页面数 =", w.stack.count())
print("文案表格行数 =", w.line_table.rowCount(), "列数 =", w.line_table.columnCount())
print("第一行文案 =", w.line_table.item(0,2).text()[:30])
print("商品名 =", w.pi_name.text())
print("旁白开关 =", w.chk_narration.isChecked(), "音乐开关 =", w.chk_music.isChecked())
print("提醒 =", w.note_missing.text())
w.final_result.setPlainText("成片成功：exports\\阶段五_三轨全开.mp4\n轨道：{'narration': True, 'music': True, 'duck': True}\n校验：720x1280 30fps 12.0s")
w.grab().save("tests/gui_stage5_audio.png")
print("截图已保存")
QTimer.singleShot(200, app.quit)
sys.exit(app.exec())
