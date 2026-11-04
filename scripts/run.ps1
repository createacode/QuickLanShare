#Requires -Version 7.0
<#
.SYNOPSIS
    开发态启动 QuickLanShare（使用项目内 .venv）。
#>
[CmdletBinding()]
param(
    [switch]$Debug
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw '未找到 uv，请先安装：https://docs.astral.sh/uv/'
}

uv sync --frozen
if ($Debug) {
    uv run python main.py --debug
}
else {
    uv run python main.py
}
