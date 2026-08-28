"""Basic setup checks for the Gate 5 OpenRouter weather agent."""

import asyncio
import importlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIENT_ROOT = Path(__file__).resolve().parent
SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8085/mcp")


def check_environment() -> bool:
    print("🔍 Checking repository environment...")
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    configured = True
    for name in ("OPENROUTER_API_KEY", "WEATHERAPI_KEY"):
        if os.getenv(name):
            print(f"✅ {name} configured")
        else:
            print(f"❌ {name} not configured in the repository-root .env")
            configured = False
    return configured


def check_dependencies() -> bool:
    print("\n🔍 Checking dependencies...")
    required_packages = (
        ("google.adk", "Google ADK"),
        ("litellm", "LiteLLM"),
        ("mcp", "MCP"),
        ("fastmcp", "FastMCP"),
        ("dotenv", "python-dotenv"),
        ("httpx", "httpx"),
    )
    installed = True
    for package, label in required_packages:
        try:
            importlib.import_module(package)
            print(f"✅ {label}")
        except ImportError:
            print(f"❌ {label} not installed")
            installed = False
    return installed


def check_agent_structure() -> bool:
    print("\n🔍 Checking agent structure...")
    required_files = (
        CLIENT_ROOT / "weather_agent" / "agent.py",
        CLIENT_ROOT / "weather_agent" / "__init__.py",
        CLIENT_ROOT / "verify_gate5_e2e.py",
    )
    valid = True
    for path in required_files:
        if path.exists():
            print(f"✅ {path.relative_to(REPO_ROOT)}")
        else:
            print(f"❌ {path.relative_to(REPO_ROOT)} not found")
            valid = False
    return valid


def check_mcp_server() -> bool:
    print("\n🔍 Checking local MCP server connectivity...")
    server_url = os.getenv("MCP_SERVER_URL", SERVER_URL)

    async def test_connection() -> int:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(server_url, timeout=10.0)
            return response.status_code

    try:
        status_code = asyncio.run(test_connection())
    except Exception:
        print("❌ Cannot reach the local MCP server")
        return False

    if status_code in (200, 404, 405):
        print(f"✅ MCP endpoint reachable at {server_url}")
        return True
    print(f"❌ MCP endpoint returned status {status_code}")
    return False


def check_agent_import() -> bool:
    print("\n🔍 Checking agent import...")
    sys.path.insert(0, str(CLIENT_ROOT))
    try:
        from weather_agent.agent import LITELLM_MODEL, root_agent

        print(f"✅ Agent imported successfully: {root_agent.name}")
        print(f"   MODEL={LITELLM_MODEL}")
        return True
    except Exception as exc:
        print(f"❌ Failed to import agent: {type(exc).__name__}")
        return False
    finally:
        sys.path.pop(0)


def main() -> int:
    checks = (
        check_environment(),
        check_dependencies(),
        check_agent_structure(),
        check_mcp_server(),
        check_agent_import(),
    )
    if all(checks):
        print("\n✅ All Gate 5 setup checks passed")
        return 0
    print("\n❌ Some Gate 5 setup checks failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
