"""Run the repository's safe Gate 1-5 regression checks from the root venv."""

from __future__ import annotations

import importlib.metadata
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from packaging.version import Version


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable).resolve()
SECRET_NAMES = ("OPENROUTER_API_KEY", "WEATHERAPI_KEY", "MCP_AUTH_TOKEN")


def port_is_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def run(command: list[str], *, cwd: Path = ROOT, timeout: int = 120) -> str:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    output = f"{result.stdout}\n{result.stderr}"
    for name in SECRET_NAMES:
        value = os.getenv(name)
        if value and value in output:
            raise RuntimeError("subprocess output contained a configured secret")
    if result.returncode:
        raise RuntimeError(f"command failed: {command[0]}")
    return output


def dependency_check() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    required_declarations = (
        "openai",
        "python-dotenv",
        "mcp[cli]>=1.29,<2",
        "google-adk>=2.8,<3",
        "litellm>=1.84",
        "httpx",
        "uvicorn",
    )
    if any(declaration not in requirements for declaration in required_declarations):
        raise RuntimeError("root requirements are incomplete")
    if "fastmcp" in requirements.lower():
        raise RuntimeError("external fastmcp remains in root requirements")

    versions = {
        "openai": importlib.metadata.version("openai"),
        "google-adk": importlib.metadata.version("google-adk"),
        "litellm": importlib.metadata.version("litellm"),
        "mcp": importlib.metadata.version("mcp"),
        "httpx": importlib.metadata.version("httpx"),
    }
    if Version(versions["litellm"]) < Version("1.84"):
        raise RuntimeError("LiteLLM is below the supported minimum")
    if Version(versions["mcp"]).major != 1:
        raise RuntimeError("MCP major version is unsupported")
    if versions["litellm"] in {"1.82.7", "1.82.8"}:
        raise RuntimeError("forbidden LiteLLM version")
    print("DEPENDENCY_CHECK=PASS")
    print("PACKAGE_VERSIONS=" + ",".join(f"{name}={value}" for name, value in versions.items()))


def compile_regression() -> None:
    python_files = [
        path
        for directory in ("01-function-calling", "02-mcp-basics", "03-production", "04-lab", "scripts")
        for path in (ROOT / directory).rglob("*.py")
    ]
    for path in python_files:
        run([str(PYTHON), "-m", "py_compile", str(path)], timeout=30)
    print("COMPILE_REGRESSION=PASS")


def gate1() -> None:
    output = run([str(PYTHON), "01-function-calling/weather_function_calling.py"])
    required = ("[model yêu cầu]", "[app thực thi]", "Trả lời:")
    if any(marker not in output for marker in required):
        raise RuntimeError("Gate 1 markers missing")
    print("GATE1_FUNCTION_CALLING=PASS")


def gate2() -> None:
    output = run([str(PYTHON), "weather_client.py"], cwd=ROOT / "02-mcp-basics")
    required = ("get_weather", "Hanoi", "Danang", "Haiphong")
    if any(marker not in output for marker in required):
        raise RuntimeError("Gate 2 markers missing")
    print("GATE2_MCP_STDIO=PASS")


def gate3() -> None:
    registry = run([str(PYTHON), "registry_client.py"], cwd=ROOT / "03-production")
    if any(marker not in registry for marker in ("get_weather_v2", "Best match", "Hanoi")):
        raise RuntimeError("registry markers missing")
    print("GATE3_REGISTRY=PASS")

    versioned = run([str(PYTHON), "versioned_client.py"], cwd=ROOT / "03-production")
    if any(marker not in versioned for marker in ("weather-v2", "2.0.0", "get_weather_v2", "[v1]")):
        raise RuntimeError("versioning markers missing")
    print("GATE3_VERSIONING=PASS")

    if port_is_open(8000):
        raise RuntimeError("port 8000 is already in use")
    auth_env = os.environ.copy()
    auth_env.setdefault("PYTHONIOENCODING", "utf-8")
    auth_env.pop("MCP_AUTH_TOKEN", None)
    server = subprocess.Popen(
        [str(PYTHON), "auth_server.py"],
        cwd=ROOT / "03-production",
        env=auth_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        deadline = time.monotonic() + 20
        while not port_is_open(8000) and server.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        if not port_is_open(8000):
            raise RuntimeError("auth server did not start")
        auth = run([str(PYTHON), "auth_client.py"], cwd=ROOT / "03-production")
        if any(marker not in auth for marker in ("auth", "Hanoi", "get_weather")):
            raise RuntimeError("authentication markers missing")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
    deadline = time.monotonic() + 10
    while port_is_open(8000) and time.monotonic() < deadline:
        time.sleep(0.2)
    if port_is_open(8000):
        raise RuntimeError("auth server port was not released")
    print("GATE3_AUTH=PASS")


def gate4_and_gate5() -> None:
    gate4 = run([str(PYTHON), "04-lab/mcp-server/verify_gate4_security.py"], timeout=90)
    if any(marker not in gate4 for marker in ("REAL_WEATHER_MCP_OK", "SECRET_LEAK_CHECK=PASS", "PORT_8085_RELEASED", "GATE4_SECURITY_VERIFICATION=PASS")):
        raise RuntimeError("Gate 4 markers missing")
    print("GATE4_REAL_WEATHER_SECURITY=PASS")

    gate5 = run([str(PYTHON), "04-lab/mcp-client/verify_gate5_e2e.py"], timeout=150)
    if any(marker not in gate5 for marker in ("AGENT_MCP_WEATHER_E2E=PASS", "PORT_8085_RELEASED", "WEATHER_SECRET_LEAK_CHECK=PASS", "GATE5_VERIFICATION=PASS")):
        raise RuntimeError("Gate 5 markers missing")
    print("GATE5_ADK_MCP_E2E=PASS")


def repository_hygiene() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout.splitlines()
    if ".env" in tracked:
        raise RuntimeError("tracked secret file found")
    if any(path.endswith(".DS_Store") and (ROOT / path).exists() for path in tracked):
        raise RuntimeError("tracked OS metadata file found")
    actual_secrets = [os.getenv(name) for name in SECRET_NAMES if os.getenv(name)]
    for relative in tracked:
        path = ROOT / relative
        if path.suffix.lower() not in {".py", ".md", ".txt", ".toml", ".json", ".yml", ".yaml"}:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        if any(secret in content for secret in actual_secrets):
            raise RuntimeError("configured secret found in tracked file")
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", ".env"], cwd=ROOT
    ).returncode
    if ignored != 0:
        raise RuntimeError(".env is not ignored")
    print("TRACKED_SECRET_SCAN=PASS")
    print("ENV_IGNORE_CHECK=PASS")


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    if not all(os.getenv(name) for name in ("OPENROUTER_API_KEY", "WEATHERAPI_KEY")):
        print("GATE6_STAGE_FAIL=configuration")
        return 1
    stages = (
        ("dependency", dependency_check),
        ("compile", compile_regression),
        ("gate1", gate1),
        ("gate2", gate2),
        ("gate3", gate3),
        ("gate4-5", gate4_and_gate5),
        ("hygiene", repository_hygiene),
    )
    try:
        for name, stage in stages:
            stage()
        if port_is_open(8000) or port_is_open(8085):
            raise RuntimeError("regression left a port open")
        print("PORT_CLEANUP=PASS")
        print("FULL_REGRESSION=PASS")
        return 0
    except Exception:
        print(f"GATE6_STAGE_FAIL={name}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
