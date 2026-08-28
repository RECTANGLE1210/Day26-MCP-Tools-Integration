# Lab 04 — OpenRouter ADK Agent with Local Weather MCP Server

A weather agent built with Google ADK and LiteLLM/OpenRouter that connects to a local MCP server via Streamable HTTP transport.

## Architecture

```
┌─────────────────┐   Streamable HTTP    ┌─────────────────┐      REST       ┌─────────────────┐
│   ADK Agent     │ ──────────────────── │   MCP Server    │ ─────────────── │  WeatherAPI.com │
│  (mcp-client)   │   127.0.0.1:8085/mcp │  (mcp-server)   │                 │                 │
└─────────────────┘                      └─────────────────┘                 └─────────────────┘
```

## Tools

| Tool | Description |
|------|-------------|
| `get_current_weather(city)` | Get current weather conditions for a city |
| `get_forecast(city, days)` | Get weather forecast (1–3 days) |
| `health_check()` | Verify server is running |

## ADK làm gì trong Lab này?

ADK (Agent Development Kit) đóng vai trò **MCP Client** 
```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  1. KẾT NỐI tới MCP Server qua Streamable HTTP                  │
│     StreamableHTTPConnectionParams(url="localhost:8085/mcp")    │
│                                                                 │
│  2. KHÁM PHÁ tools tự động (list_tools)                         │
│     McpToolset → tự hỏi server "anh có tool gì?"                │
│     → nhận về: get_current_weather, get_forecast, health_check  │
│                                                                 │
│  3. TRUYỀN tools cho LLM (OpenRouter qua LiteLLM)                │
│     Agent(model="openrouter/openai/gpt-4.1-mini", ...)          │
│     → Model biết nó có thể gọi 3 tools trên                      │
│                                                                 │
│  4. ĐIỀU PHỐI vòng lặp Function Calling                         │
│     User hỏi → LLM chọn tool → ADK gọi MCP Server                │
│     → nhận kết quả → đưa lại cho LLM tổng hợp                    │
│                                                                 │
│  5. CUNG CẤP giao diện web (adk web)                            │
│     → http://localhost:8000 để chat với agent                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

So với bài 02 (viết client thủ công bằng `mcp.ClientSession`), ADK giúp bạn **không phải viết vòng lặp function calling thủ công** nữa. Toàn bộ luồng list_tools → model quyết định → call_tool → model tổng hợp được ADK xử lý tự động.

## Setup

### 1. Configure the repository environment

```bash
cd ../..
copy .env.example .env
# Điền OPENROUTER_API_KEY và WEATHERAPI_KEY trong .env ở root
```

### 2. MCP Server

```bash
python 04-lab/mcp-server/weather.py
```

The server will be available at `http://127.0.0.1:8085/mcp`.

### 3. Verify the Gate 5 flow

```bash
python 04-lab/mcp-client/verify_gate5_e2e.py
```

### 4. ADK Agent (Client)

```bash
cd mcp-client
adk web
```

Open http://localhost:8000 in your browser, select `weather_agent`, and ask about the weather.

## Configuration

| Variable | Where | Description |
|----------|-------|-------------|
| `OPENROUTER_API_KEY` | root `.env` | OpenRouter API key |
| `OPENROUTER_MODEL` | root `.env` | Optional model; default `openai/gpt-4.1-mini` |
| `WEATHERAPI_KEY` | root `.env` | API key from weatherapi.com |
| `MCP_SERVER_URL` | root `.env` | Optional MCP URL; default `http://127.0.0.1:8085/mcp` |
| `PORT` | root environment | Optional server port override; default `8085` |
