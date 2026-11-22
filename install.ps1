# 鲜食葡萄储藏知识图谱问答 —— 环境安装（Windows / PowerShell）
#
# 做三件事：
#   1) 创建 .venv（优先 Python 3.12/3.11/3.10；找不到时退回 python 命令）
#   2) 安装依赖（自动处理「venv 内没有 pip」的打包版 Python：先 ensurepip 引导，
#      仍不行再用基础解释器的 pip --python 装入）
#   3) 数据校验 + 打印启动方式
#
# 用法：
#   .\install.ps1               # 安装依赖并校验数据
#   .\install.ps1 -Force        # 删除并重建 .venv
#   .\install.ps1 -SkipCheck    # 只装依赖，不做数据校验
#   .\install.ps1 -PythonExe C:\Python312\python.exe   # 指定解释器（多版本机器/排障时用）
#
# 注意：Python 3.13/3.14 下个别依赖（尤其 kuzu==0.11.3）可能还没有预编译轮子，
#       推荐使用 Python 3.12（python.org 或 Microsoft Store 安装）。安装失败时脚本以退出码 1 结束。
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

# 子进程安静模式：pip 不提示输入、不检查自身版本；避免任何交互式等待。
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PIP_NO_INPUT = "1"
$env:PYTHONIOENCODING = "utf-8"

$ws = $PSScriptRoot
Set-Location -LiteralPath $ws
$venv = Join-Path $ws ".venv"
$venvPy = Join-Path $venv "Scripts\python.exe"
$req = Join-Path $ws "requirements.txt"

Write-Host "== 安装环境：鲜食葡萄储藏知识图谱问答 ==" -ForegroundColor Green

function Invoke-Py {
    # 统一调用 Python / 子进程，返回输出与真实退出码。
    # 关键防呆：Python 不带参数会进入交互式 REPL —— 干净机器上会挂起等待输入，
    # 或 stdin 立刻 EOF 时静默退出 0（假成功）。因此空参数一律替换成无害的 -c pass。
    param([string]$Exe, [string[]]$ArgList)
    if ($null -eq $ArgList -or $ArgList.Count -eq 0) {
        $ArgList = @("-c", "pass")
    }
    try {
        $out = & $Exe @ArgList 2>&1
        $code = $LASTEXITCODE
        # 没拿到真实退出码时按失败处理，绝不把「未知」当成功
        if ($null -eq $code) { $code = 1 }
        return @{ Out = $out; Code = $code }
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
    foreach ($cand in @(
            @{ Exe = "py"; Arg = @("-3.12") }, @{ Exe = "py"; Arg = @("-3.11") },
            @{ Exe = "py"; Arg = @("-3.10") }, @{ Exe = "py"; Arg = @("-3.13") },
            @{ Exe = "python3.12"; Arg = @() }, @{ Exe = "python3.11"; Arg = @() },
            @{ Exe = "python3.10"; Arg = @() }, @{ Exe = "python"; Arg = @() },
            @{ Exe = "python3"; Arg = @() })) {
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
if ($basePy.Version -match "3\.1[345]") {
    Write-Host "  提示：3.13/3.14 下个别依赖可能缺轮子（kuzu 等）；若安装失败请换 Python 3.12。" -ForegroundColor Yellow
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
    if ($r.Code -ne 0) {
        Write-Host "  （venv 已建好，但内置 pip 引导未成功；下面会改用基础解释器的 pip 安装）" -ForegroundColor Yellow
    }
}

# 3) 装依赖：优先 venv 自带 pip；没有 pip 时先 ensurepip 引导，再退回基础解释器的 pip --python
Write-Host "[2/3] 安装依赖（requirements.txt）…"
$venvPipOk = $false
$r = Invoke-Py -Exe $venvPy -ArgList @("-m", "pip", "--version")
if ($r.Code -eq 0) {
    $venvPipOk = $true
} else {
    Write-Host "  venv 内没有 pip，尝试 ensurepip 引导…" -ForegroundColor Yellow
    $r = Invoke-Py -Exe $venvPy -ArgList @("-m", "ensurepip", "--upgrade", "--default-pip")
    $r = Invoke-Py -Exe $venvPy -ArgList @("-m", "pip", "--version")
    if ($r.Code -eq 0) { $venvPipOk = $true }
}

if ($venvPipOk) {
    Write-Host "  使用 venv 自带 pip 安装…"
    $r = Invoke-Py -Exe $venvPy -ArgList @("-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-r", $req)
} else {
    Write-Host "  venv 内仍无 pip，改用基础解释器的 pip --python 安装…" -ForegroundColor Yellow
    # 注意：pip 的 --python 是「全局选项」，必须放在子命令 install 之前，
    # 否则报 "The --python option must be placed before the pip subcommand name"。
    $pipArgs = $basePy.Arg + @("-m", "pip", "--python", $venvPy, "install",
        "--disable-pip-version-check", "--no-input", "-r", $req)
    $r = Invoke-Py -Exe $basePy.Exe -ArgList $pipArgs
}
$code = $r.Code
$pipLog = ($r.Out | Out-String)
if ($code -ne 0) {
    Write-Host $pipLog -ForegroundColor DarkGray
    Write-Host "[错误] 依赖安装失败（pip 退出码 $code）。" -ForegroundColor Red
    Write-Host "        常见原因：网络受限/代理；或当前 Python 版本缺少预编译轮子（3.13/3.14 常见）。"
    Write-Host "        1) 换 Python 3.12 重建：.\install.ps1 -Force -PythonExe C:\Python312\python.exe" -ForegroundColor Yellow
    Write-Host "        2) 用镜像重试：.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple" -ForegroundColor Yellow
    if ($pipLog -match "kuzu") {
        Write-Host "        提示：kuzu==0.11.3 暂无当前 Python 版本的预编译轮子，请换 Python 3.12。" -ForegroundColor Yellow
    }
    exit 1
}
if ($pipLog -match "Successfully installed") {
    $installed = ($pipLog -split "\r?\n" | Where-Object { $_ -match "Successfully installed" } | Select-Object -First 1)
    Write-Host ("  " + $installed.Trim())
} else {
    Write-Host "  提示：pip 未输出 'Successfully installed'（依赖可能已存在），下面用 import 自检确认。" -ForegroundColor Yellow
}

# 3.1) 不能只看退出码：在 venv 内实际 import 关键包，确认真的装齐
$probe = "import streamlit, openai, pandas, dotenv, pytest, kuzu; from importlib.metadata import version as v; print('DEPS_OK', v('streamlit'), v('openai'), v('pandas'), v('python-dotenv'), v('pytest'), v('kuzu'))"
$r = Invoke-Py -Exe $venvPy -ArgList @("-c", $probe)
$probeOut = ($r.Out | Out-String)
if ($r.Code -ne 0 -or $probeOut -notmatch "DEPS_OK") {
    Write-Host $probeOut -ForegroundColor DarkGray
    Write-Host "[错误] 依赖安装后自检失败：venv 内无法 import streamlit/openai/pandas/dotenv/pytest/kuzu。" -ForegroundColor Red
    Write-Host "        请检查上方 pip 日志，或运行 .\install.ps1 -Force 重建环境。" -ForegroundColor Yellow
    exit 1
}
$depsLine = ($probeOut -split "\r?\n" | Where-Object { $_ -match "DEPS_OK" } | Select-Object -First 1)
Write-Host ("  依赖自检通过：" + $depsLine.Trim()) -ForegroundColor Green

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
