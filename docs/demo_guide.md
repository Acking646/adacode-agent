# Demo Guide

This demo uses a two-process setup:

- Remote GPU server: serves the trained Qwen3-4B LoRA context manager.
- Local computer: runs the web console, local file tools, command execution, and the main coding-agent loop.

The main coding model can still be an OpenAI-compatible API model. The Qwen service is only used by the context manager to decide which local snippets should be kept or dropped.

## Remote Qwen Context Manager

On the GPU server:

```bash
cd /nfs-data/sdd/tydong/projects/adacode-agent
conda activate moe

nohup bash scripts/start_qwen_cm_server.sh > qwen_cm_server.log 2>&1 &
```

Check the service:

```bash
curl http://127.0.0.1:8001/v1/models
```

The LoRA adapter should appear as model id `cm`.

## Local Tunnel

On the local computer, keep this SSH window open:

```bash
ssh -L 8001:127.0.0.1:8001 user@server_host
```

Then the local web console can reach the remote context manager through:

```text
http://127.0.0.1:8001/v1
```

## Local Web Console

On the local computer:

```powershell
cd "C:\Users\LENOVO\Desktop\保研\参营及复习\5 南大软院\codeagent\adacode-agent"
$env:SILICONFLOW_API_KEY="your_key"
$env:OPENAI_BASE_URL="https://api.siliconflow.cn/v1"
$env:ADACODE_MODEL="deepseek-ai/DeepSeek-V4-Flash"
powershell -ExecutionPolicy Bypass -File scripts/start_web_local.ps1
```

Open:

```text
http://127.0.0.1:7860
```

## Suggested Video Flow

Keep the screen identity-neutral. Do not show names, school names, API keys, shell history, or account pages.

1. Reset the demo workspace.
2. Show the task: fix `event_metrics.py` so the tests pass.
3. Run manual context compression with Rule CM and show kept/dropped snippets plus compression.
4. Switch to Qwen CM, use URL `http://127.0.0.1:8001/v1`, model `cm`, and run compression again.
5. Start the agent. The agent reads local files, calls the model, edits code, runs tests, and stops when tests pass or the step limit is reached.
6. Show the patch, test output, and context tab.
7. Briefly explain the design: self-written controller loop, JSON action parser, local tool executor, rule/Qwen context manager, and reproducible evaluation with context-selection metrics.

Recommended task text:

```text
Fix the event metrics implementation so the tests pass. Preserve the public function names.
```

Recommended test command:

```text
python -m pytest -q
```

Use Rule CM if the remote Qwen service is slow during recording. Use Qwen CM for the manual compression shot so the trained model is still clearly visible in the demo.
