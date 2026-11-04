#requires -Version 5.1
<#
.SYNOPSIS
    Build the paste-ready prompt templates in docs/<language>/template.md from the parts/ fragments.

.DESCRIPTION
    parts/cpp.md and parts/python.md include shared fragments from parts/common/
    with lines of the form: @@include common/name.md
    Output is always UTF-8 without BOM and LF line endings, so builds are
    reproducible and diffs stay clean.

.PARAMETER Check
    Verify that docs/<language>/template.md is in sync with parts/ without writing files.
    Exits with code 1 when a generated file is missing or out of date.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/build-templates.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/build-templates.ps1 -Check
#>
[CmdletBinding()]
param(
    [switch]$Check
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$partsDir = Join-Path $root 'parts'
$outDir = Join-Path $root 'docs'
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Expand-Template {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string[]]$Stack = @()
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing template fragment: $Path"
    }

    $full = (Resolve-Path -LiteralPath $Path).Path
    if ($Stack -contains $full) {
        throw "Circular include detected: $full"
    }

    $lines = Get-Content -LiteralPath $full -Encoding UTF8
    $result = New-Object System.Collections.Generic.List[string]

    foreach ($line in $lines) {
        if ($line -match '^\s*@@include\s+(.+?)\s*$') {
            $relative = $Matches[1].Replace('\', '/')
            $child = Join-Path $partsDir $relative
            $expanded = Expand-Template -Path $child -Stack ($Stack + $full)
            foreach ($item in $expanded) {
                $result.Add($item)
            }
        }
        else {
            $result.Add($line)
        }
    }

    return $result.ToArray()
}

if (-not (Test-Path -LiteralPath $outDir)) {
    New-Item -ItemType Directory -Path $outDir | Out-Null
}

$sources = [ordered]@{
    'cpp'     = Join-Path $partsDir 'cpp.md'
    'python'  = Join-Path $partsDir 'python.md'
    'java'    = Join-Path $partsDir 'java.md'
    'rust'    = Join-Path $partsDir 'rust.md'
    'android' = Join-Path $partsDir 'android.md'
    'vue'     = Join-Path $partsDir 'vue.md'
}

$failed = $false

foreach ($name in $sources.Keys) {
    $source = $sources[$name]
    if (-not (Test-Path -LiteralPath $source)) {
        Write-Host "[FAIL] Missing template source: $source"
        $failed = $true
        continue
    }

    $text = (Expand-Template -Path $source) -join "`n"
    if (-not $text.EndsWith("`n")) {
        $text += "`n"
    }

    $destDir = Join-Path $outDir $name
    if (-not (Test-Path -LiteralPath $destDir)) {
        New-Item -ItemType Directory -Path $destDir | Out-Null
    }
    $dest = Join-Path $destDir 'template.md'

    if ($Check) {
        if (-not (Test-Path -LiteralPath $dest)) {
            Write-Host "[FAIL] Missing generated file: $dest"
            $failed = $true
            continue
        }

        $current = [System.IO.File]::ReadAllText($dest, $utf8)
        if ($current -ne $text) {
            Write-Host "[FAIL] $dest is out of date; run scripts/build-templates.ps1"
            $failed = $true
        }
        else {
            Write-Host "[OK]   $dest is in sync"
        }
    }
    else {
        [System.IO.File]::WriteAllText($dest, $text, $utf8)
        $lineCount = ($text -split "`n").Count - 1
        Write-Host "[OK]   Wrote $dest ($lineCount lines)"
    }
}

if ($failed) {
    exit 1
}

exit 0
