"""End-to-end verifier for the OpenRouter -> ADK -> MCP weather flow."""

import asyncio
import importlib.util
import io
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
import warnings
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

warnings.filterwarnings("ignore", message=r"\[EXPERIMENTAL\].*")
for logger_name in ("LiteLLM", "litellm"):
    logging.getLogger(logger_name).setLevel(logging.WARNING)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLIENT_ROOT = REPO_ROOT / "04-lab" / "mcp-client"
SERVER_PATH = REPO_ROOT / "04-lab" / "mcp-server" / "weather.py"
SERVER_URL = "http://127.0.0.1:8085/mcp"
PORT = 8085
START_TIMEOUT_SECONDS = 20.0
STOP_TIMEOUT_SECONDS = 5.0
QUERY = (
    "Thời tiết hiện tại ở Hà Nội thế nào, và cho tôi dự báo 2 ngày tới "
    "để tôi biết có nên mang ô không?"
)


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


def load_agent() -> Any:
    sys.path.insert(0, str(CLIENT_ROOT))
    try:
        # Keep import-time logging out of the verifier's marker-only output.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            from weather_agent.agent import (  # pylint: disable=import-outside-toplevel
                LITELLM_MODEL,
                MCP_SERVER_URL,
                root_agent,
            )
        return root_agent, LITELLM_MODEL, MCP_SERVER_URL
    finally:
        sys.path.pop(0)


def start_log_reader(process: subprocess.Popen[bytes]) -> tuple[bytearray, threading.Thread]:
    captured = bytearray()

    def read_output() -> None:
        if process.stdout is None:
            return
        for chunk in iter(lambda: process.stdout.read(4096), b""):
            captured.extend(chunk)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    return captured, reader


def stop_child(
    process: subprocess.Popen[bytes], captured: bytearray, reader: threading.Thread
) -> bytes:
    try:
        process.terminate()
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    except ProcessLookupError:
        pass
    reader.join(timeout=STOP_TIMEOUT_SECONDS)
    return bytes(captured)


def event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    return "".join(part.text for part in parts if getattr(part, "text", None))


async def run_agent(root_agent: Any) -> tuple[list[Any], str]:
    app_name = f"gate5_weather_{uuid.uuid4().hex}"
    user_id = f"gate5_user_{uuid.uuid4().hex}"
    session_id = f"gate5_session_{uuid.uuid4().hex}"
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    runner = Runner(
        app_name=app_name,
        agent=root_agent,
        session_service=session_service,
    )
    message = types.Content(role="user", parts=[types.Part(text=QUERY)])
    events = [
        event
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message,
        )
    ]
    final_text = "".join(event_text(event) for event in events if event.is_final_response())
    return events, final_text


def collect_tool_names(events: list[Any], method_name: str) -> list[str]:
    names: list[str] = []
    for event in events:
        for item in getattr(event, method_name)():
            name = getattr(item, "name", None)
            if name:
                names.append(name)
    return names


def safe_final_text(text: str, secrets: tuple[str, ...]) -> str:
    safe_text = text
    for secret in secrets:
        if secret:
            safe_text = safe_text.replace(secret, "[REDACTED]")
    return safe_text


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    load_dotenv(REPO_ROOT / ".env")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    weatherapi_key = os.getenv("WEATHERAPI_KEY")
    if not openrouter_key:
        print("OPENROUTER_CONFIG_MISSING")
        return 1
    if not weatherapi_key:
        print("WEATHERAPI_CONFIG_MISSING")
        return 1
    print("OPENROUTER_CONFIG_OK")
    print("WEATHERAPI_CONFIG_OK")

    if port_is_open():
        print("MCP_SERVER_PORT_8085_IN_USE")
        return 1

    child: subprocess.Popen[bytes] | None = None
    captured = bytearray()
    reader: threading.Thread | None = None
    server_ready = False
    agent_initialized = False
    e2e_ok = False
    port_released = False
    captured_log = b""

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
        captured, reader = start_log_reader(child)
        server_ready = wait_for_port(True, START_TIMEOUT_SECONDS)
        if server_ready:
            print("MCP_SERVER_PORT_8085_READY")
            try:
                root_agent, resolved_model, configured_url = load_agent()
                if configured_url != os.getenv("MCP_SERVER_URL", SERVER_URL):
                    raise RuntimeError("MCP endpoint configuration mismatch")
                if not resolved_model.startswith("openrouter/"):
                    raise RuntimeError("Model is not configured for OpenRouter")
                agent_initialized = True
                print("ADK_AGENT_INITIALIZED")
                print(f"MODEL={resolved_model}")
                print("OPENROUTER_MODEL_OK")

                events, final_text = asyncio.run(run_agent(root_agent))
                function_calls = collect_tool_names(events, "get_function_calls")
                function_responses = collect_tool_names(events, "get_function_responses")

                current_called = "get_current_weather" in function_calls
                forecast_called = "get_forecast" in function_calls
                current_responded = "get_current_weather" in function_responses
                forecast_responded = "get_forecast" in function_responses
                for event in events:
                    for call in event.get_function_calls():
                        print(f"TOOL_CALL: {call.name} args={call.args}")
                    for response in event.get_function_responses():
                        print(f"TOOL_RESPONSE: {response.name}")

                if current_called:
                    print("TOOL_CALL_CURRENT_WEATHER_OK")
                if forecast_called:
                    print("TOOL_CALL_FORECAST_OK")
                if current_responded:
                    print("TOOL_RESPONSE_CURRENT_WEATHER_OK")
                if forecast_responded:
                    print("TOOL_RESPONSE_FORECAST_OK")

                final_lower = final_text.casefold()
                final_ok = bool(final_text.strip()) and any(
                    phrase in final_lower
                    for phrase in ("hà nội", "thời tiết", "dự báo", "nhiệt", "mang ô")
                )
                if final_text.strip():
                    print(
                        "FINAL_RESPONSE: "
                        + safe_final_text(final_text, (openrouter_key, weatherapi_key))
                    )
                if final_ok:
                    print("FINAL_RESPONSE_OK")
                e2e_ok = (
                    current_called
                    and forecast_called
                    and current_responded
                    and forecast_responded
                    and final_ok
                )
                if e2e_ok:
                    print("AGENT_MCP_WEATHER_E2E=PASS")
            except Exception:
                e2e_ok = False
    except Exception:
        server_ready = False
    finally:
        if child is not None and reader is not None:
            captured_log = stop_child(child, captured, reader)
            port_released = wait_for_port(False, STOP_TIMEOUT_SECONDS)
            print(
                "PORT_8085_RELEASED"
                if port_released
                else "PORT_8085_STILL_IN_USE"
            )

    server_log = captured_log.decode("utf-8", errors="replace")
    if weatherapi_key in server_log:
        print("WEATHER_SECRET_LEAK_CHECK=FAIL")
        return 1
    print("WEATHER_SECRET_LEAK_CHECK=PASS")

    if not server_ready or not agent_initialized or not e2e_ok or not port_released:
        print("GATE5_VERIFICATION=FAIL")
        return 1

    print("GATE5_VERIFICATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
