import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core import duplicate_detector as dd
from pathlib import Path
import shutil, tempfile

base = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01" / "1"
f1 = base / "IMG_7522正面.MOV"
# 人为做一个完全相同的副本（不同文件名）
tmp = Path(tempfile.gettempdir()) / "copy_front.MOV"
shutil.copy2(f1, tmp)
assets = [
    {"path": str(f1), "filename": f1.name},
    {"path": str(tmp), "filename": tmp.name},
    {"path": str(base / "IMG_7523侧面转正整体.MOV"), "filename": "IMG_7523侧面转正整体.MOV"},
]
r = dd.detect(assets)
print("完全重复组数:", len(r["exact_groups"]))
for g in r["exact_groups"]:
    print("  ", [a["filename"] for a in g])
print("画面相似组数:", len(r["similar_groups"]))
for g in r["similar_groups"]:
    print("  ", [a["filename"] for a in g])
print("原始文件均未被删除:", f1.exists(), (base/"IMG_7523侧面转正整体.MOV").exists())
