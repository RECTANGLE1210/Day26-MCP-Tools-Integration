# 01 — Function Calling thuần (OpenRouter)

Tool `get_weather` được **định nghĩa schema thủ công** và **thực thi ngay trong app**.
Model chỉ quyết định gọi tool nào — app mới là nơi chạy.

```
User hỏi  →  Model quyết định gọi get_weather(city="Hà Nội")
                     │
                     ▼
              App TỰ THỰC THI hàm get_weather
                     │
                     ▼
              Model tổng hợp câu trả lời
```

## Cách chạy

```bash
pip install -r ../requirements.txt
copy ..\.env.example ..\.env  # rồi điền OPENROUTER_API_KEY trong ..\.env
python weather_function_calling.py
```

## File

| File | Mô tả |
|---|---|
| `weather_function_calling.py` | Định nghĩa schema OpenAI-compatible, thực thi tool, gọi OpenRouter, xử lý vòng lặp tool calling |

---

## Function Calling là gì? Giải thích đơn giản

Hình dung bạn có một **trợ lý ảo** rất giỏi ngôn ngữ, nhưng **không biết gì về thế giới thật** — không biết thời tiết, không truy cập được database, không gọi được API.

Function Calling là cách bạn **dạy trợ lý ảo sử dụng công cụ**:

```
Không có Function Calling:                 Có Function Calling:

User: "Thời tiết HN?"                     User: "Thời tiết HN?"
       │                                         │
       ▼                                         ▼
   ┌────────┐                                ┌────────┐
   │ Model  │                                │ Model  │
   │        │                                │        │ ← biết có tool get_weather
   │ "Tôi   │                                │ "Hãy   │
   │ không  │                                │  gọi   │
   │ biết"  │                                │ get_   │
   │        │                                │ weather│
   └────────┘                                │("HN")  │
                                             └───┬────┘
   Model bó tay vì                               │
   không có dữ liệu                              ▼
                                             App chạy hàm
                                                  │
                                                  ▼
                                             ┌────────┐
                                             │ Model  │
                                             │ "HN:   │
                                             │ 29°C,  │
                                             │ mưa"   │
                                             └────────┘
```

**Điểm mấu chốt:** Model **KHÔNG chạy** hàm. Nó chỉ nói *"hãy gọi hàm X với tham số Y"*.

---

## Minh hoạ từng bước chi tiết

User hỏi: **"Thời tiết Hà Nội và Đà Nẵng hôm nay thế nào?"**

```
Bước 1 — App chuẩn bị "hộp công cụ" cho model
═══════════════════════════════════════════════

    App định nghĩa schema THỦ CÔNG:
    ┌────────────────────────────────────────┐
    │  Tool: get_weather                     │
    │  Mô tả: "Lấy thời tiết thành phố"      │
    │  Tham số:                              │
    │    city: string (bắt buộc)             │
    │                                        │
    │   Schema viết TAY - 15 dòng code       │
    │     phải khớp với hàm thật             │
    └────────────────────────────────────────┘

Bước 2 — Gửi prompt + schema cho model
═══════════════════════════════════════

    App ──────────────────────────────────────────▶ OpenRouter
    │  "Thời tiết HN và ĐN?"                      │
    │  + schema get_weather                       │
    │                                             │
    │  Model hiểu: "À, có tool get_weather,       │
    │   tôi cần gọi nó 2 lần cho HN và ĐN"        │

Bước 3 — Model TRẢ VỀ yêu cầu gọi tool (không tự chạy!)
═════════════════════════════════════════════════════════

    OpenRouter ──────────────────────────────────▶ App
    │  tool_calls:                                  │
    │    [                                         │
    │      get_weather(city="Hà Nội"),             │
    │      get_weather(city="Đà Nẵng")             │
    │    ]                                         │
    │                                              │
    │    Model CHỈ sinh JSON — không hề chạy       │

Bước 4 — App TỰ THI HÀNH hàm get_weather
═════════════════════════════════════════

    App nhận yêu cầu → CHẠY hàm Python:
    ┌──────────────────────────────────────────┐
    │  get_weather("Hà Nội")   → "29°C, mưa"   │ ← App chạy
    │  get_weather("Đà Nẵng")  → "30°C, mây"   │ ← App chạy
    └──────────────────────────────────────────┘

Bước 5 — Gửi kết quả lại cho model tổng hợp
════════════════════════════════════════════

    App ──────────────────────────────────────────▶ OpenRouter
    │  Kết quả: HN 29°C mưa, ĐN 30°C mây         │
    │                                            │
    │  Model: "Hà Nội 29°C, mưa nhẹ 🌧️            │
    │           nhớ mang ô nhé!                  │
    │           Đà Nẵng 30°C, nhiều mây 🌤️       │
    │           thời tiết dễ chịu!"              │
```

---

## Nhìn vào code thật

3 phần quan trọng trong `weather_function_calling.py`:

**Phần 1 — Schema viết tay** (model cần biết tool trông như thế nào):

```python
# App phải TỰ MÔ TẢ tool cho model — viết tay, dễ sai
GET_WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
            "additionalProperties": False,
        },
    },
}
```

**Phần 2 — Hàm thực thi** (app tự chạy khi model yêu cầu):

```python
# App phải CÓ hàm thật để chạy — model không chạy hàm này
def get_weather(city: str) -> str:
    return json.dumps({"city": city, "nhiệt_độ": "29°C", ...})
```

**Phần 3 — Vòng lặp** (nhận yêu cầu → chạy → trả lại):

```python
while response.choices[0].message.tool_calls:
    message = response.choices[0].message
    messages.append(message.model_dump(exclude_none=True))
    for tool_call in message.tool_calls:
        args = json.loads(tool_call.function.arguments)
        result = get_weather(**args)      # ← APP chạy, không phải model
        messages.append({"role": "tool", "tool_call_id": tool_call.id,
                         "content": result})
    response = client.chat.completions.create(messages=messages, tools=TOOLS, ...)
```

---

## Luồng hoạt động

1. App định nghĩa schema tool OpenAI-compatible (tên, tham số, kiểu)
2. App gửi prompt + danh sách tool tới OpenRouter
3. Model trả về `tool_calls` — yêu cầu gọi `get_weather`
4. App **tự chạy** hàm `get_weather()` và đưa kết quả trả lại model
5. Model tổng hợp câu trả lời cuối cho user

## Nhược điểm

```
┌─────────────────────────────────────────────────────────────┐
│  ❌ Schema viết tay                                         │
│     {"type": "function", "function": {...}}               │
│     → 15+ dòng boilerplate, dễ lệch với hàm thật            │
│                                                             │
│  ❌ Tool gắn chặt trong app                                 │
│     App A có get_weather → App B muốn dùng?                 │
│     → Copy schema + hàm sang App B                          │
│     → Sửa hàm ở A? Phải nhớ sửa cả B                        │
│                                                             │
│  ❌ Mỗi provider 1 format                                   │
│     OpenAI-compatible: {"type": "function", ...}          │
│     Anthropic: {"name": ..., "input_schema": {...}}         │
│     → Đổi model = viết lại schema                           │
└─────────────────────────────────────────────────────────────┘
```

**MCP giải quyết tất cả các vấn đề trên** → xem [02-mcp-basics/](../02-mcp-basics/)

Bước tiếp theo: [02-mcp-basics/](../02-mcp-basics/) — tách tool ra MCP server độc lập.
