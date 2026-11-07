import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    key = os.environ.get("IFIND_API_KEY")
    if not key:
        raise SystemExit("IFIND_API_KEY is not set in this process.")
    headers = {
        "Authorization": f"Bearer {key}",
        "X-API-Key": key,
    }
    async with streamablehttp_client("https://api-mcp.51ifind.com/mcp", headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(json.dumps([tool.name for tool in tools.tools], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
