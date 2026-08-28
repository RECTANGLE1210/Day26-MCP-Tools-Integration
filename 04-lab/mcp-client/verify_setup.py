"""Basic setup checks for the Gate 5 OpenRouter weather agent."""

import importlib
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIENT_ROOT = Path(__file__).resolve().parent
SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8085/mcp")


def check_environment() -> bool:
    print("Checking repository environment...")
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    configured = True
    for name in ("OPENROUTER_API_KEY", "WEATHERAPI_KEY"):
        if os.getenv(name):
            print(f"PASS {name} configured")
        else:
            print(f"FAIL {name} not configured in the repository-root .env")
            configured = False
    return configured


def check_dependencies() -> bool:
    print("\nChecking dependencies...")
    required_packages = (
        ("google.adk", "Google ADK"),
        ("litellm", "LiteLLM"),
        ("mcp", "MCP"),
        ("mcp.server.fastmcp", "FastMCP (provided by MCP SDK)"),
        ("dotenv", "python-dotenv"),
        ("httpx", "httpx"),
    )
    installed = True
    for package, label in required_packages:
        try:
            importlib.import_module(package)
            print(f"PASS {label}")
        except ImportError:
            print(f"FAIL {label} not installed")
            installed = False
    return installed


def check_agent_structure() -> bool:
    print("\nChecking agent structure...")
    required_files = (
        CLIENT_ROOT / "weather_agent" / "agent.py",
        CLIENT_ROOT / "weather_agent" / "__init__.py",
        CLIENT_ROOT / "verify_gate5_e2e.py",
    )
    valid = True
    for path in required_files:
        if path.exists():
            print(f"PASS {path.relative_to(REPO_ROOT)}")
        else:
            print(f"FAIL {path.relative_to(REPO_ROOT)} not found")
            valid = False
    return valid


def check_mcp_configuration() -> bool:
    print("\nChecking local MCP server configuration...")
    server_url = os.getenv("MCP_SERVER_URL", SERVER_URL)
    parsed = urlparse(server_url)
    valid = parsed.scheme in {"http", "https"} and bool(parsed.netloc) and parsed.path.endswith("/mcp")
    if valid:
        print(f"PASS MCP endpoint configured at {server_url}")
    else:
        print("FAIL MCP_SERVER_URL must be an HTTP(S) URL ending in /mcp")
    return valid


def check_agent_import() -> bool:
    print("\nChecking agent import...")
    sys.path.insert(0, str(CLIENT_ROOT))
    try:
        from weather_agent.agent import LITELLM_MODEL, root_agent

        print(f"PASS Agent imported successfully: {root_agent.name}")
        print(f"   MODEL={LITELLM_MODEL}")
        return True
    except Exception as exc:
        print(f"FAIL Failed to import agent: {type(exc).__name__}")
        return False
    finally:
        sys.path.pop(0)


def main() -> int:
    checks = (
        check_environment(),
        check_dependencies(),
        check_agent_structure(),
        check_mcp_configuration(),
        check_agent_import(),
    )
    if all(checks):
        print("\nAll Gate 5 setup checks passed")
        return 0
    print("\nSome Gate 5 setup checks failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
