# 鲜食葡萄储藏知识图谱问答 —— 环境安装（Windows / PowerShell）
#
# 做三件事：
#   1) 创建 .venv（优先 Python 3.12/3.11/3.10；找不到时退回 python 命令）
#   2) 安装依赖（自动处理「venv 内没有 pip」的打包版 Python：用基础解释器的 pip --python 装入）
#   3) 数据校验 + 打印启动方式
#
# 用法：
#   .\install.ps1               # 安装依赖并校验数据
#   .\install.ps1 -Force        # 删除并重建 .venv
#   .\install.ps1 -SkipCheck    # 只装依赖，不做数据校验
#   .\install.ps1 -PythonExe C:\Python312\python.exe   # 指定解释器（多版本机器/排障时用）
param(
    [switch]$Force,
    [switch]$SkipCheck,
    [string]$PythonExe = ""
)

# 注意：这里刻意用 Continue —— 探测 `py -3.12` 不存在的版本时会产生 NativeCommandError，
# 用 Stop 会被当成致命错误中断安装。
$ErrorActionPreference = "Continue"
try { chcp 65001 | Out-Null } catch { }
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$ws = $PSScriptRoot
Set-Location -LiteralPath $ws
$venv = Join-Path $ws ".venv"
$venvPy = Join-Path $venv "Scripts\python.exe"
$req = Join-Path $ws "requirements.txt"

Write-Host "== 安装环境：鲜食葡萄储藏知识图谱问答 ==" -ForegroundColor Green

function Invoke-Py {
    param([string]$Exe, [string[]]$ArgList)
    try {
        $out = & $Exe @ArgList 2>&1
        return @{ Out = $out; Code = $LASTEXITCODE }
    } catch {
        return @{ Out = @("$($_.Exception.Message)"); Code = 1 }
    }
}

# 1) 找基础 Python（优先 3.12/3.11/3.10）
$basePy = $null
$candidates = @()
if ($PythonExe) {
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        Write-Host "[错误] -PythonExe 路径不存在：$PythonExe" -ForegroundColor Red
        exit 1
    }
    $candidates = @(@{ Exe = $PythonExe; Arg = @() })
} else {
    foreach ($cand in @(@{ Exe = "py"; Arg = @("-3.12") }, @{ Exe = "py"; Arg = @("-3.11") },
                        @{ Exe = "py"; Arg = @("-3.10") }, @{ Exe = "py"; Arg = @("-3.13") },
                        @{ Exe = "python"; Arg = @() }, @{ Exe = "python3"; Arg = @() })) {
        if (Get-Command $cand.Exe -ErrorAction SilentlyContinue) { $candidates += $cand }
    }
}

foreach ($cand in $candidates) {
    $r = Invoke-Py -Exe $cand.Exe -ArgList ($cand.Arg + @("--version"))
    $text = ($r.Out | Out-String)
    if ($r.Code -eq 0 -and $text -match "Python 3\.(\d+)") {
        $minor = [int]$Matches[1]
        if ($minor -ge 10) {
            $basePy = @{ Exe = $cand.Exe; Arg = $cand.Arg; Version = $text.Trim() }
            break
        }
    }
}
if (-not $basePy) {
    Write-Host "[错误] 未找到 Python 3.10+。请安装 Python 3.12（python.org 或 Microsoft Store）后重试。" -ForegroundColor Red
    Write-Host "        也可指定解释器：.\install.ps1 -PythonExe C:\Python312\python.exe" -ForegroundColor Yellow
    exit 1
}
Write-Host ("[1/3] 基础 Python：" + $basePy.Version)
if ($basePy.Version -match "3\.1[34]") {
    Write-Host "  提示：3.13/3.14 下个别依赖可能缺轮子；若安装失败请换 Python 3.12。" -ForegroundColor Yellow
}

# 2) 建 venv
if ($Force -and (Test-Path -LiteralPath $venv)) {
    Write-Host "  删除旧 .venv…"
    Remove-Item -LiteralPath $venv -Recurse -Force -ErrorAction SilentlyContinue
}
if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-Host "  创建 .venv…"
    $r = Invoke-Py -Exe $basePy.Exe -ArgList ($basePy.Arg + @("-m", "venv", $venv))
    if (-not (Test-Path -LiteralPath $venvPy)) {
        Write-Host "[错误] venv 创建失败。" -ForegroundColor Red
        Write-Host ($r.Out | Out-String) -ForegroundColor DarkGray
        Write-Host "        可改用：py -3.12 -m venv .venv，或安装 python.org 完整版后重试。" -ForegroundColor Yellow
        exit 1
    }
}

# 3) 装依赖：先尝试 venv 自带 pip；没有 pip 时用基础解释器的 pip --python 装入
Write-Host "[2/3] 安装依赖（requirements.txt）…"
$r = Invoke-Py -Exe $venvPy -Args @("-m", "pip", "--version")
$hasVenvPip = ($r.Code -eq 0)

if ($hasVenvPip) {
    $r = Invoke-Py -Exe $venvPy -Args @("-m", "pip", "install", "--disable-pip-version-check", "-r", $req)
    $code = $r.Code
} else {
    Write-Host "  venv 内无 pip，改用基础解释器的 pip --python 安装…" -ForegroundColor Yellow
    $r = Invoke-Py -Exe $basePy.Exe -ArgList ($basePy.Arg + @("-m", "pip", "--python", $venvPy,
                "install", "--disable-pip-version-check", "-r", $req))
    $code = $r.Code
}
if ($code -ne 0) {
    Write-Host ($r.Out | Out-String) -ForegroundColor DarkGray
    Write-Host "[错误] 依赖安装失败。网络受限时可用镜像重试：" -ForegroundColor Red
    Write-Host "        .\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple"
    exit 1
}

# 4) 数据校验
if (-not $SkipCheck) {
    Write-Host "[3/3] 数据校验与自检…"
    & $venvPy (Join-Path $ws "scripts\validate_data.py")
    if ($LASTEXITCODE -ne 0) { Write-Host "[错误] 数据校验未通过。" -ForegroundColor Red; exit 1 }
    & $venvPy (Join-Path $ws "scripts\validate_cypher.py")
    if ($LASTEXITCODE -ne 0) { Write-Host "[错误] Cypher 校验未通过。" -ForegroundColor Red; exit 1 }
}

Write-Host ""
Write-Host "[完成] 环境就绪。启动演示：" -ForegroundColor Green
Write-Host "   .\run.ps1" -ForegroundColor Cyan
Write-Host "（无 API Key 也能跑：默认离线模板模式；在线模式把 key 填进 .env，见 .env.example）"
