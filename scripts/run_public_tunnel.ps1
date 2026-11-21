# 本地服务 + cloudflared 快速隧道：给评委一个临时公网 https 地址（免注册/免绑卡）
#
# 前提：本地 8501 已在运行（.\run.ps1 或手动 streamlit run app.py）
# 用法：
#   .\scripts\run_public_tunnel.ps1              # 找 cloudflared → 起隧道 → 打印公网 URL
#   .\scripts\run_public_tunnel.ps1 -Port 8600
#   .\scripts\run_public_tunnel.ps1 -Stop        # 停止隧道
#
# 说明：trycloudflare.com 地址是临时的（进程重启会变），电脑需保持开机；
#      只是为了投票/现场演示，长期挂请用 Streamlit Cloud / 魔搭创空间（见 docs/deploy.md）。
param(
    [int]$Port = 8501,
    [switch]$Stop
)

$ErrorActionPreference = "Continue"
try { chcp 65001 | Out-Null } catch { }
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$ws = $PSScriptRoot | Split-Path -Parent
Set-Location -LiteralPath $ws
$log = Join-Path $ws ".tmp\cloudflared.log"
$urlFile = Join-Path $ws ".tmp\public_url.txt"

if ($Stop) {
    Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Host "[已停止] cloudflared 隧道进程" -ForegroundColor Yellow
    exit 0
}

# 1) 本地服务必须活着
try {
    $health = (Invoke-WebRequest "http://127.0.0.1:$Port/_stcore/health" -UseBasicParsing -TimeoutSec 6).Content
} catch {
    Write-Host "[错误] 本地 http://127.0.0.1:$Port 未就绪，请先运行 .\run.ps1" -ForegroundColor Red
    exit 1
}
Write-Host "[1/3] 本地服务正常：health=$health"

# 2) 找 cloudflared
$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue)
if (-not $cf) {
    Write-Host "[2/3] 未找到 cloudflared，尝试安装…"
    $light = Get-Command winget -ErrorAction SilentlyContinue
    if ($light) {
        & winget install --id Cloudflare.cloudflared -e --accept-package-agreements --accept-source-agreements 2>&1 | Select-Object -Last 3
        $cf = (Get-Command cloudflared -ErrorAction SilentlyContinue)
    }
    if (-not $cf) {
        Write-Host "  winget 未成功，尝试下载到 .tools/…"
        New-Item -ItemType Directory -Force -Path (Join-Path $ws ".tools") | Out-Null
        $target = Join-Path $ws ".tools\cloudflared.exe"
        $urls = @(
            "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
            "https://ghproxy.net/https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        )
        foreach ($u in $urls) {
            try {
                Invoke-WebRequest -Uri $u -OutFile $target -UseBasicParsing -TimeoutSec 120
                if ((Get-Item $target).Length -gt 10MB) { break }
            } catch { Write-Host ("  下载失败：" + $u) }
        }
        if (Test-Path $target) { $cf = @{ Source = $target } }
    }
}
if (-not $cf) {
    Write-Host "[失败] 未能获取 cloudflared。手动方案（任选其一）：" -ForegroundColor Yellow
    Write-Host "  1) winget install --id Cloudflare.cloudflared -e"
    Write-Host "  2) 从 https://github.com/cloudflare/cloudflared/releases 下载 exe 并加入 PATH"
    Write-Host "  3) 备选穿透（需本机 ssh）：ssh -R 80:127.0.0.1:$Port nokey@localhost.run"
    Write-Host "  4) 长期方案见 docs/deploy.md（Streamlit Cloud / 魔搭创空间）"
    exit 2
}
Write-Host ("[2/3] cloudflared：" + $cf.Source)

# 3) 起隧道并解析公网地址
Write-Host "[3/3] 启动隧道…"
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
New-Item -ItemType Directory -Force -Path (Split-Path $log -Parent) | Out-Null
if (Test-Path $log) { Remove-Item $log -Force }
Start-Process -FilePath $cf.Source -ArgumentList @(
    "tunnel", "--url", "http://127.0.0.1:$Port", "--no-autoupdate",
    "--loglevel", "info", "--logfile", $log
) -WindowStyle Hidden

$url = $null
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value; break }
    }
}
if ($url) {
    "公网地址：$url" | Out-File -LiteralPath $urlFile -Encoding utf8
    Write-Host ""
    Write-Host "==== 公网 Demo 已就绪 ====" -ForegroundColor Green
    Write-Host "  $url"
    Write-Host "  日志：$log"
    Write-Host "  停止：.\scripts\run_public_tunnel.ps1 -Stop"
} else {
    Write-Host "[失败] 40 秒内没拿到公网地址，查看日志：$log" -ForegroundColor Yellow
    Write-Host "        备选：ssh -R 80:127.0.0.1:$Port nokey@localhost.run"
    exit 1
}
