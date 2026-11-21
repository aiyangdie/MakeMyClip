import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QEventLoop
from app.ui.main_window import MainWindow
from app import db as dbmod, config
from pathlib import Path

app = QApplication(sys.argv)
w = MainWindow()
# 建一个真实测试项目
p = config.DB_DIR / "_gui_analysis.db"
if p.exists(): p.unlink()
w.db = dbmod.ProjectDB(str(p))
w.db.set_project_name("GUI分析测试")
w.db.init_storyboards(config.DEFAULT_STORYBOARD_TEMPLATE)
w.project_path = str(p)
# 导入一条真实素材
f = Path.home()/"Desktop"/"T26单抽视频"/"视屏素材01"/"1"/"IMG_7520整体+细节.MOV"
from app import media
info = media.probe(str(f))
info["thumb_path"] = media.make_thumb(str(f), info["duration_ms"])
w.db.add_asset(info)
w.nav.setCurrentRow(2)
w.refresh_analysis()
print("GUI分析页: 初始片段数 =", w.clip_table.rowCount())
# 触发真实分析（同步跑 AnalyzeWorker 的逻辑，直接调用核心）
from app.core import scene_detector
r = scene_detector.analyze_video(str(f))
w.db.save_scene_analysis(w.db.get_assets()[0]["id"], r, {})
w.refresh_analysis()
print("GUI分析页: 分析后片段数 =", w.clip_table.rowCount())
print("GUI分析页: 第一行 =", [w.clip_table.item(0,c).text() for c in range(7)])
pix = w.grab()
pix.save("tests/gui_analysis.png")
print("GUI分析页: 截图已保存")
QTimer.singleShot(200, app.quit)
sys.exit(app.exec())
