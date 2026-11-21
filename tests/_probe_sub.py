import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
from app.core import subtitle
from app import media

lines = [
    {"text":"这款床头柜的整体外观","start_ms":0,"end_ms":3000},
    {"text":"台面细节与边缘处理","start_ms":3000,"end_ms":6000},
    {"text":"抽屉可以平稳开合","start_ms":6000,"end_ms":9000},
    {"text":"灯光切换不同照明效果","start_ms":9000,"end_ms":12000},
]
srt = Path("tests/_probe.srt")
r = subtitle.build_srt(lines, srt)
print("SRT生成:", r["ok"], "条数", r["count"], "大小", srt.stat().st_size)
print("SRT首行:", srt.read_text(encoding='utf-8-sig').split('\n')[:4])
video = Path("exports/_stage4_test_final.mp4")
burned = Path("tests/_probe_burned.mp4")
r2 = subtitle.burn_subtitles(str(video), str(srt), str(burned),
                             style={"font":"Microsoft YaHei","size":40,"color":"#FFFFFF","outline":2,"alignment":2,"margin_v":40},
                             enabled=True)
print("烧字幕:", "OK" if r2["ok"] else "FAIL", "|", r2["error"][:200])
if r2["ok"]:
    info = media.probe(str(burned)); print("  时长",info.get("duration_ms"),"尺寸",info.get("width"),"x",info.get("height"))
# 关字幕=原样复制
off = Path("tests/_probe_no_sub.mp4")
r3 = subtitle.burn_subtitles(str(video), str(srt), str(off), enabled=False)
print("关字幕:", "OK" if r3["ok"] else "FAIL", "| skipped", r3.get("skipped"))
