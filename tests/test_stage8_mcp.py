# -*- coding: utf-8 -*-
"""阶段八 MCP 冒烟测试：真实启动 mcp_server.py（stdio），列出全部工具并调用一个只读工具。"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


async def main():
    params = StdioServerParameters(
        command=str(ROOT / ".venv" / "Scripts" / "python.exe"),
        args=[str(ROOT / "mcp_server.py")])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("工具清单(%d):" % len(names))
            for n in names:
                print("  -", n)
            assert len(names) >= 10, "工具数量不足"
            # 调一个只读工具：list_projects
            r = await session.call_tool("list_projects", {})
            data = json.loads(r.content[0].text)
            print("调用「list_projects」:", "ok, 项目数 =", len(data["projects"]))
            assert data.get("projects"), "项目列表为空"
            # 调带参数的只读工具
            proj = data["projects"][0]["name"]
            r2 = await session.call_tool("list_shots", {"project": proj})
            d2 = json.loads(r2.content[0].text)
            n_shots = len(d2.get("shots", []))
            print(f"调用「list_shots」({proj}): {n_shots} 个镜头")
            # 护栏验证：未确认导出必须被拒
            r3 = await session.call_tool("export_video", {
                "project": proj, "output_name": "_mcp_guard_test.mp4", "confirm": False})
            d3 = json.loads(r3.content[0].text)
            print("护栏验证(未确认导出):", d3["error"][:40], "...")
            assert not d3.get("ok") and "同意" in d3.get("error", ""), "护栏失效！"
            print("\nMCP 冒烟测试全部通过：服务器可用、工具可调、护栏生效。")


asyncio.run(main())
