"""MCP Server có Versioning — minh hoạ backward compatibility.

Khi tool thay đổi schema (thêm/bớt tham số, đổi kiểu trả về), client cũ
sẽ bị break nếu không có chiến lược versioning. Ví dụ này minh hoạ 3 kỹ thuật:

  1. Tool mới song song (get_weather_v2) — giữ tool cũ cho client legacy
  2. Tham số optional với default — thêm tính năng mà không break client cũ
  3. Server version trong metadata — client kiểm tra version trước khi gọi

Cách chạy:
    pip install -r ../requirements.txt
    python versioned_server.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

SERVER_VERSION = "2.0.0"

mcp = FastMCP(
    "weather-v2",
    instructions=f"Weather MCP Server v{SERVER_VERSION}. "
    "Hỗ trợ get_weather (v1, backward compat) và get_weather_v2 (chi tiết hơn).",
)

_MOCK_DB = {
    "Hanoi": {
        "temp": 29,
        "condition": "trời mưa",
        "humidity": 82,
        "wind_speed": 12,
        "forecast": [
            {"day": "tomorrow", "temp": 27, "condition": "mưa nhẹ"},
            {"day": "day_after", "temp": 31, "condition": "nắng"},
        ],
    },
    "Danang": {
        "temp": 30,
        "condition": "nhiều mây",
        "humidity": 78,
        "wind_speed": 10,
        "forecast": [
            {"day": "tomorrow", "temp": 32, "condition": "nắng"},
            {"day": "day_after", "temp": 29, "condition": "mưa rào"},
        ],
    },
}


# ── Tool v1 (giữ nguyên cho backward compatibility) ──────────────────
@mcp.tool()
def get_weather(city: str) -> str:
    """[v1] Lấy thời tiết hiện tại — trả chuỗi đơn giản. Deprecated, dùng get_weather_v2."""
    data = _MOCK_DB.get(city)
    if data:
        return f"{city}: {data['temp']}°C, {data['condition']}"
    return f"{city}: 28°C, không có dữ liệu chi tiết"


# ── Tool v2 (thêm tính năng, không break v1) ─────────────────────────
@mcp.tool()
def get_weather_v2(
    city: str,
    include_forecast: bool = False,
    units: str = "celsius",
) -> str:
    """[v2] Lấy thời tiết chi tiết — JSON, hỗ trợ forecast và đơn vị đo.

    Args:
        city: Tên thành phố (ví dụ: Hanoi, Danang)
        include_forecast: Có trả thêm dự báo 2 ngày tới không (mặc định: False)
        units: Đơn vị nhiệt độ — "celsius" hoặc "fahrenheit" (mặc định: celsius)
    """
    data = _MOCK_DB.get(city)
    if not data:
        return json.dumps(
            {"city": city, "error": "không có dữ liệu", "api_version": "2.0"},
            ensure_ascii=False,
        )

    temp = data["temp"]
    if units == "fahrenheit":
        temp = round(temp * 9 / 5 + 32, 1)

    result: dict = {
        "api_version": "2.0",
        "city": city,
        "temp": temp,
        "units": units,
        "condition": data["condition"],
        "humidity": data["humidity"],
        "wind_speed_kmh": data["wind_speed"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if include_forecast:
        result["forecast"] = data["forecast"]

    return json.dumps(result, ensure_ascii=False)


# ── Resource: server metadata (client dùng để kiểm tra version) ──────
@mcp.resource("server://info")
def server_info() -> str:
    """Metadata của server — version, supported tools, deprecation notices."""
    return json.dumps(
        {
            "name": "weather-v2",
            "version": SERVER_VERSION,
            "deprecated_tools": ["get_weather"],
            "migration_guide": "Chuyển từ get_weather sang get_weather_v2. "
            "Tham số 'city' giữ nguyên, thêm include_forecast và units.",
        },
        ensure_ascii=False,
    )


if __name__ == "__main__":
    mcp.run()
