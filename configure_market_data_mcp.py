import json
import os
import shutil
from datetime import datetime
from pathlib import Path


RUNTIME_ROOT = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp"
)
PYTHON = Path(r"C:\Users\seacy\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")
TUSHARE_SERVER = RUNTIME_ROOT / "tushare_mcp_server.py"
TUSHARE_DB = RUNTIME_ROOT / "data" / "tushare_cache.sqlite"
CLAUDE_MCP = Path(r"C:\Users\seacy\.claude\mcp.json")
CODEX_CONFIG = Path(r"C:\Users\seacy\.codex\config.toml")


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, target)
    return target


def configure_claude() -> Path:
    CLAUDE_MCP.parent.mkdir(parents=True, exist_ok=True)
    if CLAUDE_MCP.exists():
        backup(CLAUDE_MCP)
        data = json.loads(CLAUDE_MCP.read_text(encoding="utf-8"))
    else:
        data = {}
    servers = data.setdefault("mcpServers", {})
    servers["tushare-a-share"] = {
        "command": str(PYTHON),
        "args": ["-X", "utf8", str(TUSHARE_SERVER)],
    }
    servers["ifind-finance-data"] = {
        "url": "https://api-mcp.51ifind.com/mcp",
        "headers": {
            "Authorization": "Bearer ${IFIND_API_KEY}",
            "X-API-Key": "${IFIND_API_KEY}",
        },
    }
    CLAUDE_MCP.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return CLAUDE_MCP


def toml_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def strip_codex_server_blocks(text: str) -> str:
    lines = text.splitlines()
    cleaned = []
    skip = False
    target_headers = {"[mcp_servers.tushare-a-share]", "[mcp_servers.ifind-finance-data]"}
    for line in lines:
        stripped = line.strip()
        if stripped == "# WJ strategy market data MCP servers":
            continue
        if stripped in target_headers:
            skip = True
            continue
        if skip and stripped.startswith("[") and stripped.endswith("]"):
            skip = False
        if not skip:
            cleaned.append(line)
    return "\n".join(cleaned).rstrip() + "\n"


def configure_codex() -> Path:
    CODEX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    text = CODEX_CONFIG.read_text(encoding="utf-8") if CODEX_CONFIG.exists() else ""
    if CODEX_CONFIG.exists():
        backup(CODEX_CONFIG)

    blocks = (
        "\n# WJ strategy market data MCP servers\n"
        "\n[mcp_servers.tushare-a-share]\n"
        f"command = {toml_literal(str(PYTHON))}\n"
        f"args = ['-X', 'utf8', {toml_literal(str(TUSHARE_SERVER))}]\n"
        "\n[mcp_servers.ifind-finance-data]\n"
        "url = 'https://api-mcp.51ifind.com/mcp'\n"
        "headers = { Authorization = 'Bearer ${IFIND_API_KEY}', X-API-Key = '${IFIND_API_KEY}' }\n"
    )
    CODEX_CONFIG.write_text(strip_codex_server_blocks(text) + blocks, encoding="utf-8")
    return CODEX_CONFIG


def token_presence() -> dict[str, bool]:
    return {
        "IFIND_API_KEY": bool(os.environ.get("IFIND_API_KEY")),
        "TUSHARE_TOKEN": bool(os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_PRO_TOKEN")),
    }


if __name__ == "__main__":
    paths = {
        "claude_mcp": str(configure_claude()),
        "codex_config": str(configure_codex()),
        "tushare_server": str(TUSHARE_SERVER),
        "tushare_cache_db": str(TUSHARE_DB),
        "token_presence": token_presence(),
    }
    print(json.dumps(paths, ensure_ascii=False, indent=2))
