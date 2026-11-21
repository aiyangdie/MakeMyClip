import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.scene_detector import analyze_video
from pathlib import Path

base = Path.home() / "Desktop" / "T26单抽视频"
targets = [
    base / "视屏素材01" / "1" / "IMG_7520整体+细节.MOV",
    base / "视屏素材01" / "3" / "IMG_7530三色灯切换.MOV",
    base / "视屏素材01" / "3" / "IMG_7524开关抽屉.MOV",
    base / "视屏素材01" / "4" / "IMG_7540旋转灯头7-11.MOV",
]
for t in targets:
    r = analyze_video(str(t))
    print("="*60)
    print(t.name, "ok=", r["ok"], "时长", r["duration_ms"]/1000, "s", "采样", r["sample_count"], "帧")
    print("  镜头数:", len(r["shots"]))
    for s in r["shots"]:
        print(f'    镜头{s["index"]}: {s["start_ms"]/1000:.1f}-{s["end_ms"]/1000:.1f}s')
    print("  切点:", [(b["time_ms"]/1000, b["reason"]) for b in r["boundaries"]])
    print("  灯光事件:", [(e["time_ms"]/1000, e["delta"]) for e in r["light_events"]])
