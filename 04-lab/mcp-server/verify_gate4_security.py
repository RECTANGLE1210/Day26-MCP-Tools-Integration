"""Small Windows-friendly verifier for Gate 4 weather MCP security."""

import asyncio
import importlib.util
import io
import logging
import os
import socket
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = REPO_ROOT / "04-lab" / "mcp-server" / "weather.py"
SERVER_URL = "http://127.0.0.1:8085/mcp"
PORT = 8085
START_TIMEOUT_SECONDS = 20.0
STOP_TIMEOUT_SECONDS = 5.0

for logger_name in ("mcp", "mcp.client", "mcp.client.streamable_http"):
    logging.getLogger(logger_name).setLevel(logging.WARNING)


def port_is_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            return True
    except OSError:
        return False


def wait_for_port(expected_open: bool, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_is_open() == expected_open:
            return True
        time.sleep(0.2)
    return port_is_open() == expected_open


def load_weather_module() -> Any:
    spec = importlib.util.spec_from_file_location("gate4_weather", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load weather.py")

    module = importlib.util.module_from_spec(spec)
    # weather.py prints startup information at import; keep verifier output concise.
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        spec.loader.exec_module(module)
    return module


def run_offline_redaction_test(weather_module: Any) -> None:
    fake_secret = "super-secret-test-value"
    url = (
        "https://api.weatherapi.com/v1/current.json?"
        "q=Hanoi&key=super-secret-test-value&aqi=no"
    )
    assert fake_secret not in weather_module.redact_secrets(url)

    original_key = weather_module.API_KEY
    try:
        weather_module.API_KEY = fake_secret
        assert fake_secret not in weather_module.redact_secrets(
            "request failed with super-secret-test-value"
        )
    finally:
        weather_module.API_KEY = original_key

    assert weather_module.redact_secrets("ordinary diagnostic text") == (
        "ordinary diagnostic text"
    )


def tool_result_text(result: Any) -> str:
    text_parts = [
        item.text
        for item in getattr(result, "content", [])
        if getattr(item, "text", None)
    ]
    return "\n".join(text_parts)


def assert_weather_result(result: Any, forbidden: tuple[str, ...]) -> None:
    text = tool_result_text(result)
    lowered = text.casefold()
    if getattr(result, "isError", False) or not text or any(
        marker in lowered for marker in forbidden
    ):
        raise RuntimeError("Weather MCP tool returned an error result")


async def run_mcp_checks() -> None:
    async with streamable_http_client(SERVER_URL) as streams:
        read_stream, write_stream = streams[:2]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            required_tools = {
                "get_current_weather",
                "get_forecast",
                "health_check",
            }
            if not required_tools.issubset(tool_names):
                raise RuntimeError("Required MCP tools are missing")

            health = await session.call_tool("health_check")
            assert_weather_result(health, ("error", "not configured"))

            current = await session.call_tool(
                "get_current_weather", {"city": "Hanoi"}
            )
            assert_weather_result(current, ("unable to fetch", "not configured", "error"))

            forecast = await session.call_tool(
                "get_forecast", {"city": "Hanoi", "days": 1}
            )
            assert_weather_result(
                forecast, ("unable to fetch", "not configured", "error")
            )


def stop_child(process: subprocess.Popen[bytes]) -> bytes:
    process.terminate()
    try:
        output, _ = process.communicate(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate()
    return output or b""


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.getenv("WEATHERAPI_KEY")
    if not api_key:
        print("WEATHERAPI_KEY is not configured in the repository root .env")
        return 1

    try:
        weather_module = load_weather_module()
        for name in (
            "redact_secrets",
            "get_current_weather",
            "get_forecast",
            "health_check",
        ):
            if not hasattr(weather_module, name):
                raise RuntimeError(f"weather.py is missing {name}")
        run_offline_redaction_test(weather_module)
    except Exception:
        print("OFFLINE_REDACTION_TEST=FAIL")
        return 1
    print("OFFLINE_REDACTION_TEST=PASS")

    if port_is_open():
        print("MCP_SERVER_PORT_8085_IN_USE")
        return 1

    child: subprocess.Popen[bytes] | None = None
    captured_log = b""
    server_ready = False
    mcp_checks_ok = False
    port_released = False

    try:
        child_environment = os.environ.copy()
        child_environment["PORT"] = str(PORT)
        child_environment["PYTHONUNBUFFERED"] = "1"
        child_environment["PYTHONIOENCODING"] = "utf-8"
        child = subprocess.Popen(
            [sys.executable, str(SERVER_PATH)],
            cwd=REPO_ROOT,
            env=child_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        server_ready = wait_for_port(True, START_TIMEOUT_SECONDS)
        if server_ready:
            print("MCP_SERVER_PORT_8085_READY")
            try:
                asyncio.run(run_mcp_checks())
                mcp_checks_ok = True
            except Exception:
                mcp_checks_ok = False
    except Exception:
        server_ready = False
    finally:
        if child is not None:
            try:
                captured_log = stop_child(child)
            except Exception:
                captured_log = b""
            port_released = wait_for_port(False, STOP_TIMEOUT_SECONDS)
            print(
                "PORT_8085_RELEASED"
                if port_released
                else "PORT_8085_STILL_IN_USE"
            )

    if not server_ready or not mcp_checks_ok:
        print("MCP_E2E_CHECKS=FAIL")
    else:
        print("MCP_TOOLS_OK")
        print("HEALTH_CHECK_OK")
        print("CURRENT_WEATHER_OK")
        print("FORECAST_OK")
        print("REAL_WEATHER_MCP_OK")

    captured_text = captured_log.decode("utf-8", errors="replace")
    if api_key in captured_text:
        print("SECRET_LEAK_CHECK=FAIL")
        return 1
    print("SECRET_LEAK_CHECK=PASS")

    if not server_ready or not mcp_checks_ok or not port_released:
        return 1

    print("GATE4_SECURITY_VERIFICATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
