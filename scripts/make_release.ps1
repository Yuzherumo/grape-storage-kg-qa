# 生成「可交付的干净快照」：dist/<name>-<version>.zip + 校验和 + 清单
#
# 打包原则（白名单）：
#   只收录运行/评审必需的文件：源码、数据、图谱脚本、测试、文档、入口脚本、依赖清单、许可。
# 排除（黑名单，且会在打包后强校验）：
#   .env（含真实 API Key）、*.pdf（第三方论文，版权原因不随包分发）、.venv/.tools/.tmp/.refs、
#   .git、__pycache__、.pytest_cache、dist、*.log
#
# 用法：
#   .\scripts\make_release.ps1                      # 校验+测试+打包
#   .\scripts\make_release.ps1 -SkipTests           # 跳过测试（只做数据/Cypher 校验）
#   .\scripts\make_release.ps1 -Version v1.1        # 指定版本号
#   .\scripts\make_release.ps1 -WithGitBundle       # 额外生成 git bundle（保留开发历史，原创证据）
param(
    [string]$Version = "v1.0",
    [switch]$SkipTests,
    [switch]$WithGitBundle
)

$ErrorActionPreference = "Stop"
try { chcp 65001 | Out-Null } catch { }
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$ws = $PSScriptRoot | Split-Path -Parent
Set-Location -LiteralPath $ws
$venvPy = Join-Path $ws ".venv\Scripts\python.exe"
$name = "grape-storage-kg-qa"
$dist = Join-Path $ws "dist"
$stage = Join-Path $ws ".tmp\release\$name"
$zip = Join-Path $dist "$name-$Version.zip"

if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-Host "[错误] 未找到 .venv，请先运行 .\install.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "== 打包 $name $Version ==" -ForegroundColor Green

# 0) 打包前自检
Write-Host "[1/5] 数据 / Cypher 校验…"
& $venvPy (Join-Path $ws "scripts\validate_data.py") | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "[错误] 数据校验失败，停止打包。" -ForegroundColor Red; exit 1 }
& $venvPy (Join-Path $ws "scripts\validate_cypher.py") | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "[错误] Cypher 校验失败，停止打包。" -ForegroundColor Red; exit 1 }

if (-not $SkipTests) {
    Write-Host "[2/5] 离线测试…"
    & $venvPy -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { Write-Host "[错误] 测试失败，停止打包。" -ForegroundColor Red; exit 1 }
} else {
    Write-Host "[2/5] 跳过测试（-SkipTests）"
}

# 1) 白名单暂存
Write-Host "[3/5] 收集白名单文件…"
if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

$files = @(
    "README.md", "LICENSE", "requirements.txt", "pyproject.toml", "pytest.ini",
    ".env.example", ".gitignore", "run.ps1", "install.ps1", "app.py"
)
$dirs = @("app", "data", "graph", "scripts", "tests", "docs", ".github", ".streamlit")

foreach ($f in $files) {
    if (Test-Path -LiteralPath (Join-Path $ws $f)) { Copy-Item -LiteralPath (Join-Path $ws $f) -Destination $stage -Force }
}
foreach ($d in $dirs) {
    $src = Join-Path $ws $d
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $dst = Join-Path $stage $d
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    Get-ChildItem -LiteralPath $src -Recurse -File | Where-Object {
        $_.FullName -notmatch "\\__pycache__\\|\\\.pytest_cache\\|\.pyc$|\.pdf$|\\_shots\\|secrets\.toml$"
    } | ForEach-Object {
        $rel = $_.FullName.Substring($src.Length).TrimStart("\")
        $target = Join-Path $dst $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
}

# 2) 打包
Write-Host "[4/5] 压缩…"
New-Item -ItemType Directory -Force -Path $dist | Out-Null
if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal

# 3) 强校验：压缩包里绝不能出现敏感/版权文件
Write-Host "[5/5] 校验压缩包内容…"
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
$entries = $archive.Entries | ForEach-Object { $_.FullName }
$archive.Dispose()
$forbidden = $entries | Where-Object {
    $_ -match "(^|/)\.env$" -or $_ -match "secrets\.toml$" -or $_ -match "\.pdf$" -or $_ -match "(^|/)\.venv" -or
    $_ -match "(^|/)\.refs" -or $_ -match "(^|/)\.tools" -or $_ -match "(^|/)\.tmp" -or
    $_ -match "(^|/)\.git/" -or $_ -match "__pycache__" -or $_ -match "pytest-cache"
}
if ($forbidden) {
    Write-Host "[错误] 压缩包含禁止文件：" -ForegroundColor Red
    $forbidden | Select-Object -First 10 | ForEach-Object { Write-Host "  - $_" }
    exit 1
}

$zipInfo = Get-Item $zip
$sha = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
$shaFile = "$zip.sha256"
"$sha  $name-$Version.zip" | Out-File -LiteralPath $shaFile -Encoding utf8

$manifest = Join-Path $dist "MANIFEST-$Version.md"
$lines = @(
    "# 交付包清单（$name $Version）",
    "",
    "- 生成时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "- 压缩包：``$name-$Version.zip``（$([math]::Round($zipInfo.Length/1KB,1)) KB，$($entries.Count) 个文件）",
    "- SHA256：``$sha``（见同名 .sha256 文件）",
    "",
    "## 包含（白名单）",
    "- 源码：``app/``（问答管线/双后端/UI）",
    "- 数据：``data/``（entities/triples/sources/schema/黄金集）",
    "- 图谱：``graph/``（schema + 生成物 + 10 个查询模板）",
    "- 脚本：``scripts/``（校验/生成/评测/导入/打包）",
    "- 测试：``tests/``（pytest 全绿，离线可跑，无 API Key 依赖；具体数量以本次运行输出为准）",
    "- 文档：``docs/``（api/spec/sources/eval/neo4j_verify/demo/submission/ai_usage 等）",
    "- 入口：``README.md``、``install.ps1``、``run.ps1``、``app.py``、``requirements.txt``、``.env.example``、``pyproject.toml``、``pytest.ini``、``LICENSE``",
    "- 部署：``.streamlit/config.toml``（主题）、``.streamlit/secrets.toml.example``（Secrets 模板）、``docs/deploy.md``（云端部署步骤）",
    "",
    "## 排除（及原因）",
    "- ``.env``：含真实 API Key，仅本机使用（模板见 ``.env.example``）",
    "- ``.streamlit/secrets.toml``：云端密钥文件，不随包分发（模板见 ``.streamlit/secrets.toml.example``）",
    "- ``*.pdf``：第三方论文/标准 PDF，版权原因不随包分发（仅引用题录与条级摘录，见 ``docs/sources.md``）",
    "- ``.venv/.tools/.tmp/.refs``：本机环境/下载物/缓存",
    "- ``.git``：可用 ``git bundle`` 另附开发历史（``-WithGitBundle``）",
    "- ``__pycache__/.pytest_cache/dist``：缓存与产物",
    "",
    "## 评审如何运行",
    "1. 解压后运行 ``.\install.ps1``（自动建 .venv 并装依赖；Windows + Python 3.10+）",
    "2. 运行 ``.\run.ps1`` → 浏览器打开 ``http://127.0.0.1:8501``",
    "3. 无 API Key 时自动离线模板模式；在线模式把 key 填进 ``.env``（见 ``.env.example``）",
    "4. 自检：``.\run.ps1 -Check``（数据十项 + Cypher 静态校验 + 图谱加载）",
    ""
)
$lines | Out-File -LiteralPath $manifest -Encoding utf8

if ($WithGitBundle) {
    $bundle = Join-Path $dist "$name-$Version.bundle"
    git bundle create $bundle --all | Out-Null
    Write-Host "[附加] git bundle：$bundle"
}

Write-Host ""
Write-Host "==== 打包完成 ====" -ForegroundColor Green
Write-Host "  包：$zip"
Write-Host "  大小：$([math]::Round($zipInfo.Length/1KB,1)) KB | 文件数：$($entries.Count)"
Write-Host "  SHA256：$sha"
Write-Host "  清单：$manifest"
Write-Host "  校验和：$shaFile"
