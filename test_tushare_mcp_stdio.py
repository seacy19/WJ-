import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(
        command=r"C:\Users\seacy\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
        args=[
            "-X",
            "utf8",
            r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\tushare_mcp_server.py",
        ],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(json.dumps([tool.name for tool in tools.tools], ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
