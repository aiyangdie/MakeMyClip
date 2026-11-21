# -*- coding: utf-8 -*-
"""全局配置：路径、常量、默认分镜模板。"""
from pathlib import Path

APP_NAME = "MakeMyClip"
APP_VERSION = "0.1.0"
STAGE = "第一阶段 · 基础工作台"

# 程序根目录（MakeMyClip/）
ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "projects"
CACHE_DIR = ROOT / "cache"
THUMB_DIR = CACHE_DIR / "thumbnails"
EXPORT_DIR = ROOT / "exports"
LOG_DIR = ROOT / "logs"
RECENT_FILE = CACHE_DIR / "recent_projects.json"

for _d in (DB_DIR, THUMB_DIR, EXPORT_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv", ".flv", ".webm"}

# 阶段四：成片比例/分辨率/帧率映射（保持商品比例，填充不拉伸）
# 阶段七增补 3:4：淘宝官方口径——主图视频 9:16 上传后商详页不展示，
# 推荐 3:4 或 1:1；纯新增选项，不影响已有比例。
EXPORT_SIZES = {
    "9:16 竖屏": {"720p": (720, 1280), "1080p": (1080, 1920)},
    "3:4 竖版": {"720p": (720, 960), "1080p": (1080, 1440)},
    "16:9 横屏": {"720p": (1280, 720), "1080p": (1920, 1080)},
    "1:1 正方形": {"720p": (720, 720), "1080p": (1080, 1080)},
}
RENDER_CACHE_DIR = CACHE_DIR / "render"   # 中间片段缓存（每个镜头独立文件）
RENDER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 编码质量 -> CRF（越小越清晰）
QUALITY_CRF = {"标准": 23, "高质量": 19, "最高": 15}

# 阶段六增补：转场与停留默认值（可在界面/导出参数覆盖）
# transition: "none"=硬切(原行为) / "fade"=叠化；改参数不影响单镜头缓存。
DEFAULT_TRANSITION = "fade"       # 用户要求过渡自然，默认叠化；设 "none" 即回退硬切
DEFAULT_TRANSITION_S = 0.4        # 叠化时长（秒）
DEFAULT_MIN_HOLD_MS = 0            # 【阶段七改为0】节奏改由"每镜头建议时长 target_ms"管理
                                   # （按淘宝主图视频最佳时长 15-30 秒分配）；此值仅作全局兜底。
DEFAULT_SUB_TRANSITION_S = 0.4    # 联动镜头内部两段之间的短叠化

# 阶段十增补：字幕/配音风格（参考真实淘宝主图视频模板，可在界面切换回退）
# subtitle_style: "standard"=原完整句白字字幕 / "selling_badge"=卖点标签排版
# voice_mode: "bgm_only"=参考片风格(纯平稳BGM,无念稿) / "narration"=中文旁白 / "silent"=静音
DEFAULT_SUBTITLE_STYLE = "selling_badge"   # 用户要求按参考片模板优化，默认卖点标签
DEFAULT_VOICE_MODE = "bgm_only"             # 参考片无逐句念稿，默认纯BGM
DEFAULT_BGM_VOLUME = 0.5                    # 本地合成BGM整体音量

# 首版默认分镜模板（可在界面增删改）
DEFAULT_STORYBOARD_TEMPLATE = [
    "产品整体亮相",
    "台面材质和边缘",
    "拉手特写",
    "抽屉开合",
    "抽屉内部",
    "柜脚和底部",
    "灯杆调节",
    "灯头旋转",
    "三色温切换",
    "灯罩细节",
    "实体开关按钮",
    "整体收尾",
]

# 分镜识别状态（任务书第七节）
ANALYSIS_STATES = [
    "未分析",
    "已找到候选",
    "候选待核验",
    "已确认",
    "需要人工选择",
    "未找到合适素材",
    "分析失败",
]
