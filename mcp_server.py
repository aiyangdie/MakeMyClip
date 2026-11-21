# -*- coding: utf-8 -*-
"""MakeMyClip 智能体剪辑 MCP 服务器（阶段八新增）。

用法（WorkBuddy 自定义连接器登记示例）：
    command: <项目>/.venv/Scripts/python.exe
    args:    ["<项目>/mcp_server.py"]

工具名遵守 MCP 官方命名规范（ASCII），中文含义写在描述里，智能体按描述理解。
安全护栏（详见 app/commands.py，全部焊死在代码里）：
- 原始素材只读；锁定镜头任何工具都改不动（数据库层强制）。
- export_video 必须先取得用户明确同意（confirm=True），否则拒绝执行。
- 所有操作写入 logs/agent_ops.log，可用 read_agent_log 审计。

智能体使用守则（写给连接到本服务器的任何智能体）：
1. 修改类操作前先用 list_shots / get_shot 看清楚现状，不要凭猜改。
2. 绝不能虚构商品结构、材质、颜色、功能、尺寸——程序只认真实素材。
3. 改完镜头后建议向用户复述改了哪个镜头、结果如何。
4. 导出前必须先向用户说明"导出什么、多长、什么比例"，用户点头后再带 confirm=True 调用。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app import commands  # noqa: E402

mcp = FastMCP("MakeMyClip 智能体剪辑")


def _ok(data):
    return json.dumps(data, ensure_ascii=False, indent=1)


def _fail(e: Exception):
    return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def list_projects() -> str:
    """【查看项目列表】列出全部剪辑项目（名称、文件、大小、修改时间）。先调这个确认项目名。"""
    try:
        return _ok({"projects": commands.list_projects()})
    except commands.CommandError as e:
        return _fail(e)


@mcp.tool()
def list_shots(project: str) -> str:
    """【列出时间线镜头】列出某项目时间线的全部镜头：名称、素材、起止秒、建议时长、是否锁定/联动/已缓存。只读。"""
    try:
        return _ok({"shots": commands.list_shots(project)})
    except commands.CommandError as e:
        return _fail(e)


@mcp.tool()
def get_shot(project: str, shot_id: int) -> str:
    """【查看镜头详情】查看单个镜头的完整信息（含素材总时长，便于判断还能取多少画面）。只读。"""
    try:
        return _ok(commands.get_shot(project, shot_id))
    except commands.CommandError as e:
        return _fail(e)


@mcp.tool()
def list_assets(project: str) -> str:
    """【列出项目素材】列出项目已导入的全部原始素材（路径、时长）。只读。换镜头素材前先在这里找真实素材。"""
    try:
        return _ok({"assets": commands.list_assets(project)})
    except commands.CommandError as e:
        return _fail(e)


@mcp.tool()
def set_shot_time(project: str, shot_id: int, start_s: float, end_s: float) -> str:
    """【修改镜头起止时间】修改单个镜头取素材的起止时间（单位秒）。只影响这一个镜头；锁定镜头会被拒绝。"""
    try:
        return _ok(commands.set_shot_time(project, shot_id, start_s, end_s))
    except commands.CommandError as e:
        return _fail(e)


@mcp.tool()
def set_shot_target(project: str, shot_id: int, target_s: float) -> str:
    """【设置镜头建议时长】设置单个镜头的建议时长（秒）。素材短则末帧定格补足，长则截短。0=不限（素材原长）。只影响这一个镜头。"""
    try:
        return _ok(commands.set_shot_target(project, shot_id, target_s))
    except commands.CommandError as e:
        return _fail(e)


@mcp.tool()
def replace_shot(project: str, shot_id: int, asset_path: str,
                start_s: float = None, end_s: float = None) -> str:
    """【替换镜头素材】替换单个镜头的画面素材。asset_path 必须来自「列出项目素材」的真实素材，不能虚构。锁定镜头会被拒绝。"""
    try:
        return _ok(commands.replace_shot(project, shot_id, asset_path, start_s, end_s))
    except commands.CommandError as e:
        return _fail(e)


@mcp.tool()
def reorder_shots(project: str, shot_ids_in_order: list) -> str:
    """【调整镜头顺序】按新顺序重排时间线镜头。shot_ids_in_order 必须包含全部镜头各一次（缺镜头也算）。"""
    try:
        return _ok(commands.reorder_shots(project, shot_ids_in_order))
    except commands.CommandError as e:
        return _fail(e)


@mcp.tool()
def export_video(project: str, output_name: str, confirm: bool = False,
                 ratio: str = "3:4 竖版", res: str = "720p", fps: int = 30,
                 quality: str = "标准", transition: str = None) -> str:
    """【导出成片】渲染并导出 MP4。硬性护栏：confirm=False 一律拒绝——必须先向用户
    说明导出内容并取得明确同意，再以 confirm=True 调用。比例可选：9:16 竖屏、
    3:4 竖版（淘宝商详推荐）、16:9 横屏、1:1 正方形。transition 可选 fade（叠化）/none（硬切）。"""
    try:
        return _ok(commands.export_video(project, output_name, confirm=confirm,
                                         ratio=ratio, res=res, fps=fps,
                                         quality=quality, transition=transition))
    except commands.CommandError as e:
        return _fail(e)


@mcp.tool()
def read_agent_log(tail: int = 20) -> str:
    """【查看智能体操作日志】查看最近的智能体操作记录（审计：谁改了什么、导出是否经确认）。只读。"""
    return _ok({"log": commands.read_log(tail)})


if __name__ == "__main__":
    mcp.run()
