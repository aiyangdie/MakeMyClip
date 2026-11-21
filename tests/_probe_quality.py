import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.quality_scorer import score_segment, format_scores
from pathlib import Path
base = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01"
for name in ["3/IMG_7530三色灯切换.MOV", "1/IMG_7520整体+细节.MOV"]:
    f = base / name
    if not f.exists(): 
        print("跳过", name); continue
    r = score_segment(str(f), 0, 9000)
    print(name, "->", format_scores(r))
