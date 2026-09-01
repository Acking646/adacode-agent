$ErrorActionPreference = "Stop"

if (-not $env:SILICONFLOW_API_KEY) {
    Write-Host "Please set SILICONFLOW_API_KEY first."
    Write-Host '$env:SILICONFLOW_API_KEY="your_key"'
    exit 1
}

if (-not $env:OPENAI_BASE_URL) {
    $env:OPENAI_BASE_URL = "https://api.siliconflow.cn/v1"
}

if (-not $env:ADACODE_MODEL) {
    $env:ADACODE_MODEL = "deepseek-ai/DeepSeek-V4-Flash"
}

python -m web.server --host 127.0.0.1 --port 7860
