"""Minh hoa FUNCTION CALLING thuan voi OpenRouter va OpenAI SDK.

Model chi yeu cau goi tool; ung dung Python moi la noi thuc thi ``get_weather``.

Cach chay:
    pip install -r ../requirements.txt
    tao file .env o root voi OPENROUTER_API_KEY
    python weather_function_calling.py
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

DEFAULT_MODEL = "openai/gpt-4.1-mini"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
MODEL = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
BASE_URL = os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)
MAX_TOOL_ROUNDS = 8

SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý thời tiết thân thiện, trả lời bằng tiếng Việt tự nhiên. "
    "Dùng emoji phù hợp (🌧️ 🌤️ 💨 💧). Tóm tắt ngắn gọn, dễ hiểu, "
    "và đưa ra lời khuyên thực tế (ví dụ: mang ô, mặc áo mỏng)."
)

# 1. App tu dinh nghia schema cua tool theo format OpenAI-compatible.
GET_WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Lay thoi tiet hien tai cua mot thanh pho (du lieu mock).",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Ten thanh pho"},
            },
            "required": ["city"],
            "additionalProperties": False,
        },
    },
}
TOOLS = [GET_WEATHER_TOOL]


# 2. App tu thuc thi tool; day van la mock data, khong phai Weather API that.
def get_weather(city: str) -> str:
    """Tra ve thoi tiet mock cua *city*."""
    mock_data = {
        "Hà Nội": {
            "nhiệt_độ": "29°C",
            "thời_tiết": "trời mưa nhẹ",
            "độ_ẩm": "82%",
            "gió": {"hướng": "Đông Nam", "tốc_độ": "12 km/h"},
        },
        "Hồ Chí Minh": {
            "nhiệt_độ": "33°C",
            "thời_tiết": "mưa rào",
            "độ_ẩm": "75%",
            "gió": {"hướng": "Tây Nam", "tốc_độ": "15 km/h"},
        },
        "Đà Nẵng": {
            "nhiệt_độ": "30°C",
            "thời_tiết": "nhiều mây",
            "độ_ẩm": "78%",
            "gió": {"hướng": "Đông", "tốc_độ": "10 km/h"},
        },
    }
    default = {"nhiệt_độ": "28°C", "thời_tiết": "không có dữ liệu chi tiết"}
    return json.dumps({"city": city, **mock_data.get(city, default)}, ensure_ascii=False)


TOOL_HANDLERS = {"get_weather": get_weather}


def create_client() -> OpenAI:
    """Create the OpenRouter client only after validating the required key."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "Thiếu OPENROUTER_API_KEY. Hãy đặt biến này trong file .env ở root repository."
        )
    return OpenAI(api_key=api_key, base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL))


def _as_dict(value: Any) -> dict[str, Any]:
    """Convert SDK response objects to dictionaries for the next API request."""
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if hasattr(value, "dict"):
        return value.dict(exclude_none=True)
    raise TypeError("OpenAI SDK response has an unsupported message format")


def _tool_error(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def execute_tool(tool_call: Any) -> str:
    """Dispatch only registered tools and return a deterministic tool result."""
    name = tool_call.function.name
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return _tool_error(f"Tool không tồn tại: {name}")

    raw_arguments = tool_call.function.arguments
    try:
        arguments = json.loads(raw_arguments)
    except (TypeError, json.JSONDecodeError):
        return _tool_error(f"Arguments không phải JSON hợp lệ cho tool {name}")

    if (
        not isinstance(arguments, dict)
        or set(arguments) != {"city"}
        or not isinstance(arguments["city"], str)
    ):
        return _tool_error("Arguments của get_weather phải có đúng một trường city kiểu string")

    try:
        return handler(**arguments)
    except Exception as exc:
        return _tool_error(f"Không thể thực thi tool {name}: {exc}")


def run(prompt: str, client: OpenAI | None = None) -> str:
    """Run the OpenAI-compatible tool-calling loop until a final answer is returned."""
    _configure_output()
    client = client or create_client()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": prompt},
    ]

    for round_number in range(MAX_TOOL_ROUNDS + 1):
        response = client.chat.completions.create(
            model=os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL),
            messages=messages,
            tools=TOOLS,
        )
        if not getattr(response, "choices", None):
            raise RuntimeError("OpenRouter không trả về lựa chọn nào")

        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            return getattr(message, "content", None) or "Model không trả về nội dung cuối."

        if round_number >= MAX_TOOL_ROUNDS:
            raise RuntimeError(f"Vượt quá giới hạn {MAX_TOOL_ROUNDS} vòng gọi tool")

        # Giữ assistant tool_calls trong conversation trước khi thêm tool results.
        messages.append(_as_dict(message))
        for tool_call in tool_calls:
            name = tool_call.function.name
            arguments = tool_call.function.arguments
            print(f"  [model yêu cầu] {name}({arguments})")
            result = execute_tool(tool_call)
            print(f"  [app thực thi]  -> {result}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    raise RuntimeError("Function calling loop kết thúc bất thường")


def main() -> int:
    _configure_output()
    question = "Thời tiết Hà Nội và Đà Nẵng hôm nay thế nào?"
    try:
        client = create_client()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"User: {question}\n")
    try:
        print("Trả lời:", run(question, client=client))
    except Exception as exc:
        api_key = os.getenv("OPENROUTER_API_KEY") or ""
        message = str(exc).replace(api_key, "[redacted]") if api_key else str(exc)
        print(f"Lỗi khi gọi OpenRouter: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
