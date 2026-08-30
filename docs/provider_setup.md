# Provider Setup

AdaCode-Agent uses OpenAI-compatible chat completions.

## SiliconFlow

Set credentials through environment variables:

```bash
set SILICONFLOW_API_KEY=your_key
set OPENAI_BASE_URL=https://api.siliconflow.cn/v1
```

Run the agent:

```bash
python -m agent.main "Fix the project so tests pass." --workspace examples/demo_project --model deepseek-ai/DeepSeek-V4-Flash
```

Minimal API sanity check:

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["SILICONFLOW_API_KEY"],
    base_url="https://api.siliconflow.cn/v1",
)

resp = client.chat.completions.create(
    model="deepseek-ai/DeepSeek-V4-Flash",
    messages=[{"role": "user", "content": "你好，请只回复 OK"}],
    max_tokens=20,
)

print(resp.choices[0].message.content)
```

Never hard-code real keys in tracked files.

