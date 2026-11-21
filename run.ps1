# 鲜食葡萄储藏知识图谱问答 —— 一键启动
# 用法：
#   .\run.ps1            数据校验 + 启动 Web 演示（默认 http://127.0.0.1:8501）
#   .\run.ps1 -Check     只做数据校验与图谱自检，不启动服务
#   .\run.ps1 -Port 8600 指定端口
param(
    [switch]$Check,
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"
try { chcp 65001 | Out-Null } catch { }
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$OutputEncoding = [System.Text.Encoding]::UTF8

$ws = $PSScriptRoot
Set-Location -LiteralPath $ws
$venvPy = Join-Path $ws ".venv\Scripts\python.exe"

Write-Host "== 鲜食葡萄储藏知识图谱问答 ==" -ForegroundColor Green

if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-Host "[错误] 未找到 .venv。请先按 README「环境准备」创建虚拟环境并安装依赖。" -ForegroundColor Red
    exit 1
}

Write-Host "[1/3] 数据校验（九项）..."
& $venvPy (Join-Path $ws "scripts\validate_data.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 数据校验未通过，已中止启动。" -ForegroundColor Red
    exit 1
}

Write-Host "[2/3] 图谱加载自检..."
& $venvPy -c "from app.store import get_store; s=get_store(); print('  后端:', s.name, '| 统计:', s.stats())"
if ($LASTEXITCODE -ne 0) { Write-Host "[错误] 图谱加载失败。" -ForegroundColor Red; exit 1 }

if ($Check) {
    Write-Host "[3/3] 跳过启动（-Check）。" -ForegroundColor Yellow
    exit 0
}

Write-Host "[3/3] 启动 Web 演示： http://127.0.0.1:$Port" -ForegroundColor Cyan
& $venvPy -m streamlit run (Join-Path $ws "app\ui.py") --server.port $Port --server.headless true --browser.gatherUsageStats false
