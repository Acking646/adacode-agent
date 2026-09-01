param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"

if ($env:ADACODE_WEB_HOST -and -not $PSBoundParameters.ContainsKey("HostName")) {
    $HostName = $env:ADACODE_WEB_HOST
}

if ($env:ADACODE_WEB_PORT -and -not $PSBoundParameters.ContainsKey("Port")) {
    $Port = [int]$env:ADACODE_WEB_PORT
}

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

python -m web.server --host $HostName --port $Port
