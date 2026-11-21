# 便携版 Neo4j 实跑环境（无需管理员、无需 Docker、无需 Aura 账号）
#
# 做三件事：
#   1) 下载便携 JDK 21（Temurin）+ Neo4j 5 社区版 zip 到 .tools/（已 gitignore）
#   2) 解压、设置初始密码、后台启动 Neo4j（bolt://127.0.0.1:7687）
#   3) 用自带的 cypher-shell 导入 graph/*.cypher 并校验节点/关系计数，重复导入验证幂等
#
# 用法：
#   .\scripts\setup_neo4j_portable.ps1              # 下载+启动+导入+校验
#   .\scripts\setup_neo4j_portable.ps1 -OnlyDownload
#   .\scripts\setup_neo4j_portable.ps1 -Stop
#   .\scripts\setup_neo4j_portable.ps1 -Status
#
# 密码：优先读 .env 的 NEO4J_PASSWORD，否则用默认 grape12345（仅本地验证用）
param(
    [switch]$OnlyDownload,
    [switch]$Stop,
    [switch]$Status,
    [string]$JdkZip = "",
    [string]$Neo4jZip = ""
)

$ErrorActionPreference = "Stop"
try { chcp 65001 | Out-Null } catch { }
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$ws = $PSScriptRoot | Split-Path -Parent
Set-Location -LiteralPath $ws
$tools = Join-Path $ws ".tools"
$jdkDir = Join-Path $tools "jdk21"
$neo4jDir = Join-Path $tools "neo4j"
$pass = "grape12345"

# 读 .env 里的密码（不打印）
$envFile = Join-Path $ws ".env"
if (Test-Path -LiteralPath $envFile) {
    $line = Select-String -Path $envFile -Pattern "^NEO4J_PASSWORD=(.+)$" -Encoding UTF8 | Select-Object -First 1
    if ($line -and $line.Matches[0].Groups[1].Value.Trim()) { $pass = $line.Matches[0].Groups[1].Value.Trim() }
}

function Get-Jdk {
    if (Test-Path (Join-Path $jdkDir "bin\java.exe")) { return }
    New-Item -ItemType Directory -Force -Path $tools | Out-Null
    $zip = if ($JdkZip) { $JdkZip } else { Join-Path $tools "jdk21.zip" }
    if (-not (Test-Path $zip)) {
        Write-Host "[下载] JDK 21 (Temurin, ~190MB)…"
        try {
            Invoke-WebRequest -Uri "https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse" -OutFile $zip -UseBasicParsing
        } catch {
            Write-Host "[失败] JDK 下载失败（网络受限）。请手动下载便携 JDK 21 zip 后用 -JdkZip 指定路径：" -ForegroundColor Red
            Write-Host "        .\scripts\setup_neo4j_portable.ps1 -JdkZip D:\jdk21.zip -Neo4jZip D:\neo4j.zip"
            throw
        }
    }
    Write-Host "[解压] JDK 21…"
    Expand-Archive -LiteralPath $zip -DestinationPath $jdkDir -Force
    $inner = Get-ChildItem -Path $jdkDir -Directory | Where-Object { $_.Name -like "jdk-21*" } | Select-Object -First 1
    if ($inner) {
        Get-ChildItem -Path $inner.FullName -Force | Move-Item -Destination $jdkDir -Force
        Remove-Item -LiteralPath $inner.FullName -Force -Recurse
    }
}

function Get-Neo4j {
    if (Test-Path (Join-Path $neo4jDir "bin\cypher-shell.bat")) { return }
    New-Item -ItemType Directory -Force -Path $tools | Out-Null
    $zip = if ($Neo4jZip) { $Neo4jZip } else { Join-Path $tools "neo4j.zip" }
    if (-not (Test-Path $zip)) {
        Write-Host "[下载] Neo4j 5.26 社区版 (~130MB)…"
        try {
            Invoke-WebRequest -Uri "https://dist.neo4j.org/neo4j-community-5.26.0-windows.zip" -OutFile $zip -UseBasicParsing
        } catch {
            Write-Host "[失败] Neo4j 下载失败：当前网络对 dist.neo4j.org 返回 403（详见 docs/neo4j_verify.md §1）。" -ForegroundColor Red
            Write-Host "        请手动下载 neo4j-community-5.26.0-windows.zip，然后用 -Neo4jZip 指定：" -ForegroundColor Yellow
            Write-Host "        .\scripts\setup_neo4j_portable.ps1 -JdkZip D:\jdk21.zip -Neo4jZip D:\neo4j.zip"
            throw
        }
    }
    Write-Host "[解压] Neo4j…"
    Expand-Archive -LiteralPath $zip -DestinationPath $neo4jDir -Force
    $inner = Get-ChildItem -Path $neo4jDir -Directory | Where-Object { $_.Name -like "neo4j-community-*" } | Select-Object -First 1
    if ($inner) {
        Get-ChildItem -Path $inner.FullName -Force | Move-Item -Destination $neo4jDir -Force
        Remove-Item -LiteralPath $inner.FullName -Force -Recurse
    }
}

function Get-CypherShell {
    return Join-Path $neo4jDir "bin\cypher-shell.bat"
}

Get-Jdk
Get-Neo4j
$env:JAVA_HOME = $jdkDir
$env:PATH = "$jdkDir\bin;$env:PATH"
$shell = Get-CypherShell
if (-not (Test-Path -LiteralPath $shell)) { throw "未找到 cypher-shell：$shell" }
if (-not (Test-Path (Join-Path $neo4jDir "bin\neo4j.bat"))) { throw "Neo4j 解压不完整" }

if ($Stop) {
    & (Join-Path $neo4jDir "bin\neo4j.bat") stop
    exit 0
}
if ($Status) {
    & $shell -a "bolt://127.0.0.1:7687" -u neo4j -p $pass "RETURN 1 AS ok"
    exit $LASTEXITCODE
}
if ($OnlyDownload) { Write-Host "[完成] 仅下载/解压"; exit 0 }

# 首次启动前设置初始密码（已初始化会报错，忽略）
$dbms = Join-Path $neo4jDir "data\dbms"
if (-not (Test-Path $dbms)) {
    Write-Host "[初始化] 设置初始密码…"
    & (Join-Path $neo4jDir "bin\neo4j-admin.bat") dbms set-initial-password $pass 2>&1 | Out-Null
}

Write-Host "[启动] Neo4j（后台）…"
& (Join-Path $neo4jDir "bin\neo4j.bat") start
Start-Sleep -Seconds 12

Write-Host "[导入] schema → nodes → rels…"
foreach ($f in @("schema.cypher", "init_nodes.cypher", "init_rels.cypher")) {
    $path = Join-Path $ws "graph\$f"
    if (-not (Test-Path $path)) { throw "缺少 $path" }
    Write-Host "  - $f"
    & $shell -a "bolt://127.0.0.1:7687" -u neo4j -p $pass -f $path
    if ($LASTEXITCODE -ne 0) { throw "导入失败：$f" }
}

Write-Host "[校验] 计数与幂等（再导一次）…"
$q1 = 'MATCH (n) RETURN count(n) AS nodes;'
$q2 = 'MATCH ()-[r]->() RETURN count(r) AS rels;'
$nodes1 = (& $shell -a "bolt://127.0.0.1:7687" -u neo4j -p $pass --format plain $q1 | Select-Object -Last 1)
$rels1 = (& $shell -a "bolt://127.0.0.1:7687" -u neo4j -p $pass --format plain $q2 | Select-Object -Last 1)
foreach ($f in @("init_nodes.cypher", "init_rels.cypher")) {
    & $shell -a "bolt://127.0.0.1:7687" -u neo4j -p $pass -f (Join-Path $ws "graph\$f") | Out-Null
}
$nodes2 = (& $shell -a "bolt://127.0.0.1:7687" -u neo4j -p $pass --format plain $q1 | Select-Object -Last 1)
$rels2 = (& $shell -a "bolt://127.0.0.1:7687" -u neo4j -p $pass --format plain $q2 | Select-Object -Last 1)

Write-Host ""
Write-Host "==== 结果 ===="
Write-Host "Java:        $((& "$jdkDir\bin\java.exe" -version 2>&1 | Select-Object -First 1))"
Write-Host "Neo4j:       $neo4jDir"
Write-Host "节点数:      $nodes1（二次导入后 $nodes2）"
Write-Host "关系数:      $rels1（二次导入后 $rels2）"
Write-Host "Bolt:        bolt://127.0.0.1:7687  user=neo4j"
if ($nodes1 -eq $nodes2 -and $rels1 -eq $rels2) {
    Write-Host "[通过] 导入幂等（二次导入计数不变）" -ForegroundColor Green
} else {
    Write-Host "[失败] 二次导入计数变化，导入不幂等" -ForegroundColor Red
    exit 1
}
Write-Host "停止服务：.\scripts\setup_neo4j_portable.ps1 -Stop"
