import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core import video_editor as ve
from pathlib import Path
f = Path.home()/"Desktop"/"T26单抽视频"/"视屏素材01"/"1"/"IMG_7520整体+细节.MOV"
shot = {"shot_id":"t1","asset_path":str(f),"start_ms":0,"end_ms":3000,"crop":""}
ep = {"ratio":"9:16 竖屏","res":"720p","fps":30,"crf":23}
print("目标尺寸:", ve.target_size(ep["ratio"], ep["res"]))
print("cache_key:", ve.cache_key_for(shot, ep))
r = ve.render_shot(shot, ep)
print("渲染:", "OK" if r["ok"] else "FAIL", "缓存命中:", r["cached"], r["error"][:200])
if r["ok"]:
    p = ve.probe_output(r["path"])
    print("中间片段校验:", p)
# 缓存命中测试
r2 = ve.render_shot(shot, ep)
print("二次渲染缓存命中:", r2["cached"])
# 拼接测试：两个镜头
f2 = Path.home()/"Desktop"/"T26单抽视频"/"视屏素材01"/"3"/"IMG_7530三色灯切换.MOV"
shot2 = {"shot_id":"t2","asset_path":str(f2),"start_ms":1000,"end_ms":4000,"crop":""}
r3 = ve.render_shot(shot2, ep)
segs = [{"shot_id":"t1","path":r["path"]},{"shot_id":"t2","path":r3["path"]}]
out = ve.concat_segments(segs, "tests/_probe_final.mp4")
print("拼接:", "OK" if out["ok"] else "FAIL", out.get("error","")[:200])
if out["ok"]:
    print("成片校验:", ve.probe_output(out["path"]))
