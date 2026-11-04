#Requires -Version 7.0
<#
.SYNOPSIS
    一键构建 QuickLanShare Windows x64 便携发布包（PyInstaller onedir）。

.DESCRIPTION
    依次执行：uv 环境同步 → ruff → mypy → pytest → 版本同步 → 生成 exe 版本资源
    → PyInstaller 打包 → 整理 exe 同级目录 → SHA256SUMS → ZIP。

.PARAMETER SkipTests
    跳过测试与覆盖率（仅用于快速出包，正式发布前必须完整执行）。

.PARAMETER NoZip
    只生成发布目录，不生成 zip。

.EXAMPLE
    pwsh -File scripts/build.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$NoZip
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# 让 uv / python / pyinstaller 的中文输出在 Windows 控制台正常显示
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$BuildDate = Get-Date -Format 'yyyy-MM-dd'

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param([string]$Name, [scriptblock]$Action)
    $global:LASTEXITCODE = 0
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Name 失败（退出码 $LASTEXITCODE）"
    }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw '未找到 uv。请先安装 uv 并确保在 PATH 中：https://docs.astral.sh/uv/'
}
if (-not (Test-Path 'app.ico')) {
    throw '缺少 app.ico，无法生成窗口图标与 exe 图标。'
}

Write-Step '同步依赖（uv sync --frozen）'
Invoke-Checked 'uv sync' { uv sync --frozen }

Write-Step '代码风格检查（ruff）'
Invoke-Checked 'ruff check' { uv run ruff check . }
Invoke-Checked 'ruff format --check' { uv run ruff format --check . }

Write-Step '类型检查（mypy）'
Invoke-Checked 'mypy' { uv run mypy }

if (-not $SkipTests) {
    Write-Step '运行测试与覆盖率（core / services）'
    Invoke-Checked 'pytest' {
        uv run pytest --cov=quicklanshare.services --cov=quicklanshare.core --cov-report=term-missing
    }
}
else {
    Write-Warning '已跳过测试；正式发布前必须去掉 -SkipTests 重新构建。'
}

Write-Step '同步版本与版权'
Invoke-Checked 'sync_version' { uv run python scripts/sync_version.py --build-date $BuildDate }
Invoke-Checked 'gen_version_info' { uv run python scripts/gen_version_info.py }
Invoke-Checked 'verify_version' { uv run python scripts/verify_version.py }

$versionLine = Select-String -Path 'src\quicklanshare\core\version.py' -Pattern '^__version__ = "(.+)"$'
$Version = $versionLine.Matches[0].Groups[1].Value
$ReleaseName = "QuickLanShare_v${Version}_win-x64_$(($BuildDate -replace '-', ''))"

Write-Step "PyInstaller 打包（${ReleaseName}）"
if (Test-Path 'build') { Remove-Item -Recurse -Force 'build' }
if (Test-Path 'dist') { Remove-Item -Recurse -Force 'dist' }
Invoke-Checked 'pyinstaller' {
    uv run pyinstaller --noconfirm --clean --windowed --onedir `
        --name 'QuickLanShare' `
        --icon 'app.ico' `
        --version-file 'scripts/version_info.txt' `
        --add-data 'app.ico;.' `
        --add-data 'client;client' `
        --hidden-import 'aiohttp' `
        --hidden-import 'aiofiles' `
        --hidden-import 'qrcode' `
        --hidden-import 'PIL.Image' `
        main.py
}

$exePath = Join-Path $Root 'dist\QuickLanShare\QuickLanShare.exe'
if (-not (Test-Path $exePath)) {
    throw "未生成 exe：$exePath"
}
$platformPlugin = Join-Path $Root 'dist\QuickLanShare\_internal\PySide6\plugins\platforms\qwindows.dll'
if (-not (Test-Path $platformPlugin)) {
    throw "Qt 平台插件缺失：$platformPlugin。请检查 PySide6 安装或使用 --collect-all PySide6 重新打包。"
}

Write-Step '整理发布目录'
$releaseRoot = Join-Path $Root 'release'
$releaseDir = Join-Path $releaseRoot $ReleaseName
if (Test-Path $releaseDir) {
    $resolved = (Resolve-Path $releaseDir).Path
    if (-not $resolved.StartsWith((Resolve-Path $releaseRoot).Path)) {
        throw "拒绝删除非发布目录：$resolved"
    }
    Remove-Item -Recurse -Force $releaseDir
}
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
Copy-Item -Path 'dist\QuickLanShare\*' -Destination $releaseDir -Recurse -Force

Copy-Item -LiteralPath 'README.md' -Destination $releaseDir -Force
Copy-Item -LiteralPath 'VERSION.txt' -Destination $releaseDir -Force
Copy-Item -LiteralPath 'THIRD-PARTY-NOTICES.md' -Destination $releaseDir -Force
Copy-Item -LiteralPath 'LICENSE' -Destination $releaseDir -Force
$docsTarget = Join-Path $releaseDir 'docs'
New-Item -ItemType Directory -Force -Path $docsTarget | Out-Null
Copy-Item -LiteralPath 'docs\readme.md' -Destination $docsTarget -Force
Copy-Item -LiteralPath 'docs\develop-readme.md' -Destination $docsTarget -Force
if (Test-Path 'docs\images') {
    Copy-Item -Path 'docs\images' -Destination $docsTarget -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $releaseDir 'config') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $releaseDir 'logs') | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $releaseDir 'config\.gitkeep') | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $releaseDir 'logs\.gitkeep') | Out-Null

Write-Step '生成 SHA256SUMS.txt'
$sumsPath = Join-Path $releaseDir 'SHA256SUMS.txt'
$lines = Get-ChildItem -Path $releaseDir -Recurse -File |
    Where-Object { $_.FullName -ne $sumsPath } |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($releaseDir.Length + 1).Replace('\', '/')
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        "$hash  $relative"
    }
$lines | Set-Content -LiteralPath $sumsPath -Encoding utf8

if (-not $NoZip) {
    Write-Step '生成 ZIP 压缩包'
    $zipPath = Join-Path $releaseRoot "$ReleaseName.zip"
    if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
    Compress-Archive -Path (Join-Path $releaseDir '*') -DestinationPath $zipPath -CompressionLevel Optimal
}

$sizeMb = [math]::Round((Get-ChildItem -Path $releaseDir -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
Write-Host ""
Write-Host "构建完成：$ReleaseName" -ForegroundColor Green
Write-Host "  发布目录：$releaseDir"
Write-Host "  可执行文件：$exePath"
Write-Host "  目录大小：$sizeMb MB"
if (-not $NoZip) {
    Write-Host "  ZIP：$(Join-Path $releaseRoot "$ReleaseName.zip")"
}
