"""Drive a running obsidian-blade-mcp over stdio and print what a client sees.

Usage: python scripts/smoke.py [command [args...]]
Default command: ``uvx obsidian-blade-mcp`` (the published package).
Set OBSIDIAN_VAULT_PATH first. Exit code is 1 when the handshake, the tool
count or a vault_info call fails.
"""

from __future__ import annotations

import asyncio
import sys

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def main(argv: list[str]) -> int:
    command, args = (argv[0], argv[1:]) if argv else ("uvx", ["obsidian-blade-mcp"])
    async with Client(StdioTransport(command, args)) as client:
        info = client.initialize_result.serverInfo
        print(f"server: {info.name} {info.version}")
        tools = await client.list_tools()
        print(f"tools: {len(tools)}")
        if len(tools) not in (28, 40):
            print("unexpected tool count (expected 28 read-only or 40 with writes)")
            return 1
        result = await client.call_tool("vault_info", {})
        text = result.content[0].text if result.content else ""
        print(text)
        return 0 if "[backend:" in text else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
