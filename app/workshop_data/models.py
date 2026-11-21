# -*- coding: utf-8 -*-
"""阶段 B · 工作台数据适配层（视图模型）

边界（严格遵守任务书）：
  - 本包**只读** ProjectDB，绝不写库、绝不改既有表结构。
  - 不 import app.ui.wizard / app.ui.main_window（避免与旧界面耦合）。
  - 所有派生规则集中在这里，UI 层不得再写业务判断。

核心概念：**分析来源必须如实区分**
  analyzer_kind = "heuristic"  基础算法测量（OpenCV），不是 AI 理解
                = "vlm"        本地视觉模型
                = "cloud"      云端模型
                = ""           未分析
  当前产品只有 heuristic，因此 UI 必须显示"基础算法分析"，不得写成"AI 已理解商品"。
"""
from dataclasses import dataclass, field
from typing import List, Optional

# ============================================================================
# 一、五态（任务书要求：未分析 / 分析中 / 已完成基础测量 / 需要人工确认 / 分析失败）
# ============================================================================
ST_UNANALYZED = "unanalyzed"      # 未分析
ST_ANALYZING = "analyzing"        # 分析中（运行时状态，不落库）
ST_MEASURED = "measured"          # 已完成基础测量（仅算法，非 AI）
ST_CONFIRM = "confirm"            # 需要人工确认
ST_FAILED = "failed"              # 分析失败

STATUS_LABEL = {
    ST_UNANALYZED: "未分析",
    ST_ANALYZING: "分析中",
    ST_MEASURED: "已基础测量",
    ST_CONFIRM: "待人工确认",
    ST_FAILED: "分析失败",
}

# 状态 → 语义色档（UI 按此取色，不在界面里写死颜色）
STATUS_TONE = {
    ST_UNANALYZED: "muted",
    ST_ANALYZING: "info",
    ST_MEASURED: "success",
    ST_CONFIRM: "warning",
    ST_FAILED: "danger",
}

# 分析来源 → 人话说明（这是"不得冒充 AI"的关键落点）
ANALYZER_LABEL = {
    "": "未分析",
    "heuristic": "基础算法测量（画面变化/亮度/清晰度，非 AI 理解）",
    "vlm": "本地视觉模型识别",
    "cloud": "云端模型识别",
}


# ============================================================================
# 二、视图模型
# ============================================================================
@dataclass
class AssetVM:
    """一条素材在界面上的样子。"""
    asset_id: int
    path: str
    filename: str
    is_image: bool
    duration_ms: int
    width: int
    height: int
    fps: float
    thumb_path: str
    group: str
    status: str                       # 五态之一
    status_label: str
    status_tone: str
    pending_count: int = 0            # 该素材下待人工确认的候选数
    shot_count: int = 0
    decode_ok: bool = True
    error: str = ""
    analyzer_kind: str = ""           # ""/heuristic/vlm/cloud
    analyzer_label: str = ""
    note: str = ""                    # 给用户看的一句话说明

    @property
    def size_text(self) -> str:
        if self.width and self.height:
            return f"{self.width}×{self.height}"
        return "—"

    @property
    def duration_text(self) -> str:
        if self.is_image:
            return "静帧"
        if not self.duration_ms:
            return "--:--"
        s = self.duration_ms // 1000
        return f"{s // 60:02d}:{s % 60:02d}"

    @property
    def kind_text(self) -> str:
        return "图片" if self.is_image else "视频"


@dataclass
class GroupVM:
    """素材分组（按真实所在文件夹，或用户覆盖）。"""
    name: str
    count: int


@dataclass
class AssetStats:
    """素材工作台顶部的统计条。"""
    total: int = 0
    unanalyzed: int = 0
    analyzing: int = 0
    measured: int = 0
    confirm: int = 0
    failed: int = 0
    images: int = 0
    videos: int = 0

    @property
    def analyzed(self) -> int:
        """真正做过分析的（测量完成 + 待确认）"""
        return self.measured + self.confirm

    @property
    def progress_pct(self) -> int:
        if not self.total:
            return 0
        return round(self.analyzed / self.total * 100)


@dataclass
class SegmentVM:
    """剪辑方案页用的镜头视图（阶段 C 才实现界面，这里先定义契约）。"""
    shot_id: str
    seq: int
    name: str
    asset_path: str
    start_ms: int
    end_ms: int
    duration_ms: int
    target_ms: int
    locked: bool
    thumb_path: str
    subtitle: str = ""
    l1: List[str] = field(default_factory=list)     # 可观察动作
    l2: str = ""                                     # 商品功能
    l2_confirmed: Optional[bool] = None              # None=无声明（当前一律 None）
    action_source: str = "heuristic"                 # heuristic/vlm/cloud/none
    has_asset: bool = True

    @property
    def duration_text(self) -> str:
        return f"{self.duration_ms / 1000:.1f}s"

    @property
    def range_text(self) -> str:
        return f"{self.start_ms / 1000:.1f}–{self.end_ms / 1000:.1f}s"


@dataclass
class CheckItemVM:
    """导出前自检项（阶段 D 用，先定义契约）。"""
    level: str          # ok / warn / bad
    title: str
    detail: str


@dataclass
class ProjectVM:
    """一个项目的整体视图。"""
    db_path: str
    name: str
    assets: List[AssetVM] = field(default_factory=list)
    groups: List[GroupVM] = field(default_factory=list)
    stats: AssetStats = field(default_factory=AssetStats)
    product_info: dict = field(default_factory=dict)
    timeline_count: int = 0
    storyboard_count: int = 0
    warnings: List[str] = field(default_factory=list)
