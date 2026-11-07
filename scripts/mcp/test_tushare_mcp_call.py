import asyncio
import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    child_env = os.environ.copy()
    child_env["MARKET_DATA_MCP_PLAINTEXT_SECRET_FILE"] = (
        r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a"
        r"\market_data_mcp\.market_data_mcp_secrets.json"
    )
    params = StdioServerParameters(
        command=r"C:\Users\seacy\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
        args=[
            "-X",
            "utf8",
            r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\tushare_mcp_server.py",
        ],
        env=child_env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            diag = await session.call_tool("token_diagnostics", {})
            print("DIAG")
            print(diag.content[0].text)
            result = await session.call_tool(
                "stock_basic",
                {
                    "exchange": "",
                    "list_status": "L",
                    "limit": 3,
                    "use_cache": False,
                },
            )
            payload = result.content[0].text
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                print(payload)
                return
            print(json.dumps(
                {
                    "source": data.get("source"),
                    "row_count": data.get("row_count"),
                    "returned_count": data.get("returned_count"),
                    "first_rows": data.get("rows", [])[:3],
                },
                ensure_ascii=False,
                indent=2,
            ))


if __name__ == "__main__":
    asyncio.run(main())
