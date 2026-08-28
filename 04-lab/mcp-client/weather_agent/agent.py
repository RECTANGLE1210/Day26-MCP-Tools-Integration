"""Gate 5 agent: OpenRouter LLM orchestrating tools from the Weather MCP server."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool.mcp_toolset import (
    McpToolset,
    StreamableHTTPConnectionParams,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

DEFAULT_MODEL = "openai/gpt-4.1-mini"
DEFAULT_MCP_SERVER_URL = "http://127.0.0.1:8085/mcp"


def get_litellm_model_name(model: str | None = None) -> str:
    """Resolve an OpenRouter model name to LiteLLM's provider format."""
    model_name = model or os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL
    return model_name if model_name.startswith("openrouter/") else f"openrouter/{model_name}"


if not os.getenv("OPENROUTER_API_KEY"):
    raise RuntimeError(
        "OPENROUTER_API_KEY is required in the repository root .env or environment."
    )

OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL)
LITELLM_MODEL = get_litellm_model_name(OPENROUTER_MODEL)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Initializing Weather MCP agent")
logger.info("MCP endpoint: %s", MCP_SERVER_URL)
logger.info("MODEL=%s", LITELLM_MODEL)

weather_tools = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=MCP_SERVER_URL,
        timeout=30.0,
    )
)

root_agent = Agent(
    name="weather_agent",
    model=LiteLlm(model=LITELLM_MODEL),
    tools=[weather_tools],
    instruction=(
        "Bạn là trợ lý thời tiết thân thiện. Với câu hỏi về thời tiết hiện tại "
        "hoặc dự báo, bắt buộc dùng các MCP weather tools; không tự bịa dữ liệu "
        "từ memory của model. Dùng get_current_weather cho hiện tại, "
        "get_forecast cho dự báo, và chỉ gọi health_check khi cần kiểm tra server. "
        "Trả lời cuối cùng ngắn gọn, thân thiện, bằng ngôn ngữ của người dùng."
    ),
)
logger.info("Weather agent initialized with MCP tools")
