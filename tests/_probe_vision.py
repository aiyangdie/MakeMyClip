import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.ai.vision_provider import provider_factory
from pathlib import Path

base = Path.home() / "Desktop" / "T26单抽视频" / "视屏素材01"
targets = [
    base / "3" / "IMG_7530三色灯切换.MOV",
    base / "3" / "IMG_7524开关抽屉.MOV",
    base / "4" / "IMG_7540旋转灯头7-11.MOV",
    base / "1" / "IMG_7520整体+细节.MOV",
]
p = provider_factory()
for t in targets:
    if not t.exists():
        print("跳过(不存在):", t.name); continue
    print("="*66)
    print(t.name)
    r = p.analyze_segment(str(t), 0, 16000)
    print("  ok=", r["ok"], "| 灯光状态数=", r["metrics"].get("light_state_count"),
          "| 暖冷跨度=", r["metrics"].get("warm_span"),
          "| 亮度跨度=", r["metrics"].get("brightness_span"))
    print("  运动max=", r["metrics"].get("motion_max"), "| 肤色max=", r["metrics"].get("skin_ratio_max"))
    print("  建议标签:", r["suggested_tags"], "| 需核验:", r["need_review"])
    for lab in r["labels"]:
        print(f'    - {lab["name"]} (置信{lab["confidence"]}, 核验{lab["need_review"]})')
