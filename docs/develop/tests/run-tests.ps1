#requires -Version 5.1
<#
.SYNOPSIS
    Tests for the template build and validation scripts.

.DESCRIPTION
    Runs the repository checks, then repeats destructive checks inside a
    temporary copy of the repository. The working tree is never modified.
    This file is ASCII-only on purpose: Windows PowerShell 5.1 reads BOM-less
    scripts with the ANSI code page.

.PARAMETER KeepTemp
    Keep the temporary sandbox directories for debugging.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tests/run-tests.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tests/run-tests.ps1 -KeepTemp
#>
[CmdletBinding()]
param(
    [switch]$KeepTemp
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$utf8 = New-Object System.Text.UTF8Encoding($false)

$script:passed = 0
$script:failed = 0

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

function New-Sandbox {
    $dir = Join-Path $env:TEMP ("develop-tests-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $dir | Out-Null

    Get-ChildItem -LiteralPath $repoRoot -Force |
        Where-Object { $_.Name -ne '.git' } |
        ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $dir -Recurse -Force
        }

    return $dir
}

function Remove-Sandbox {
    param([string]$Path)
    if ($KeepTemp) {
        Write-Host "       kept sandbox: $Path"
        return
    }
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Invoke-RepoScript {
    param(
        [string]$Root,
        [string]$Relative,
        [string[]]$ScriptArgs = @()
    )

    $path = Join-Path $Root $Relative
    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $path @ScriptArgs 2>&1
    $code = $LASTEXITCODE

    return [pscustomobject]@{
        ExitCode = $code
        Output   = (($output | Out-String).Trim())
    }
}

function Test-Case {
    param(
        [string]$Name,
        [scriptblock]$Body
    )

    try {
        & $Body
        Write-Host "[PASS] $Name"
        $script:passed++
    }
    catch {
        Write-Host "[FAIL] $Name"
        Write-Host "       $($_.Exception.Message)"
        $script:failed++
    }
}

# ---------------------------------------------------------------------------
# Positive checks against the real working tree
# ---------------------------------------------------------------------------
Test-Case 'generated templates are in sync' {
    $result = Invoke-RepoScript -Root $repoRoot -Relative 'scripts/build-templates.ps1' -ScriptArgs @('-Check')
    Assert-True ($result.ExitCode -eq 0) "expected exit 0, got $($result.ExitCode): $($result.Output)"
    Assert-True ($result.Output -match 'in sync') 'output does not report sync'
}

Test-Case 'repository checks pass' {
    $result = Invoke-RepoScript -Root $repoRoot -Relative 'scripts/check-templates.ps1'
    Assert-True ($result.ExitCode -eq 0) "expected exit 0, got $($result.ExitCode): $($result.Output)"
}

Test-Case 'docs and tests layout exists' {
    $readmePath = Join-Path $repoRoot 'docs/readme.md'
    $developPath = Join-Path $repoRoot 'docs/develop-readme.md'
    $testPath = Join-Path $repoRoot 'tests/run-tests.ps1'

    Assert-True (Test-Path -LiteralPath $readmePath) 'missing docs/readme.md'
    Assert-True (Test-Path -LiteralPath $developPath) 'missing docs/develop-readme.md'
    Assert-True (Test-Path -LiteralPath $testPath) 'missing tests/run-tests.ps1'
    Assert-True (Test-Path -LiteralPath (Join-Path $repoRoot 'AGENTS.md')) 'missing AGENTS.md'
    Assert-True (Test-Path -LiteralPath (Join-Path $repoRoot 'readme.md')) 'missing readme.md'

    foreach ($name in @('cpp', 'python', 'java', 'rust', 'android', 'vue')) {
        Assert-True (Test-Path -LiteralPath (Join-Path $repoRoot "docs/$name/template.md")) "missing docs/$name/template.md"
        Assert-True (Test-Path -LiteralPath (Join-Path $repoRoot "parts/$name.md")) "missing parts/$name.md"
    }

    foreach ($name in @('screenshots', 'images', 'diagrams', 'videos')) {
        Assert-True (Test-Path -LiteralPath (Join-Path $repoRoot "cache/$name/.gitkeep")) "missing cache/$name/.gitkeep"
    }

    $readme = [System.IO.File]::ReadAllText($readmePath, [System.Text.Encoding]::UTF8)
    $develop = [System.IO.File]::ReadAllText($developPath, [System.Text.Encoding]::UTF8)

    Assert-True ($readme -match '\u5F00\u53D1\u8005') 'docs/readme.md does not address developers'
    Assert-True ($develop -match '\u5F00\u53D1\u8005') 'docs/develop-readme.md does not address developers'
}

# ---------------------------------------------------------------------------
# Negative checks inside a sandbox copy
# ---------------------------------------------------------------------------
Test-Case 'drifted template is rejected' {
    $box = New-Sandbox
    try {
        $path = Join-Path $box 'docs/cpp/template.md'
        [System.IO.File]::AppendAllText($path, "`n<!-- drift -->`n", $utf8)
        $result = Invoke-RepoScript -Root $box -Relative 'scripts/build-templates.ps1' -ScriptArgs @('-Check')
        Assert-True ($result.ExitCode -ne 0) 'drifted template was not rejected'
    }
    finally {
        Remove-Sandbox $box
    }
}

Test-Case 'missing L11 section is rejected' {
    $box = New-Sandbox
    try {
        $parts = Join-Path $box 'parts/cpp.md'
        $text = [System.IO.File]::ReadAllText($parts, [System.Text.Encoding]::UTF8)
        $text = [regex]::Replace($text, '(?m)^### L11 .*\r?\n', '')
        [System.IO.File]::WriteAllText($parts, $text, $utf8)

        $build = Invoke-RepoScript -Root $box -Relative 'scripts/build-templates.ps1'
        Assert-True ($build.ExitCode -eq 0) "build failed: $($build.Output)"

        $result = Invoke-RepoScript -Root $box -Relative 'scripts/check-templates.ps1'
        Assert-True ($result.ExitCode -ne 0) 'missing L11 was not rejected'
    }
    finally {
        Remove-Sandbox $box
    }
}

Test-Case 'old fill-in wording is rejected' {
    $box = New-Sandbox
    try {
        $parts = Join-Path $box 'parts/cpp.md'
        $phrase = -join @([char]0x53EA, [char]0x586B, [char]0x5199)  # only fill in
        [System.IO.File]::AppendAllText($parts, "`n$phrase V0`n", $utf8)

        $build = Invoke-RepoScript -Root $box -Relative 'scripts/build-templates.ps1'
        Assert-True ($build.ExitCode -eq 0) "build failed: $($build.Output)"

        $result = Invoke-RepoScript -Root $box -Relative 'scripts/check-templates.ps1'
        Assert-True ($result.ExitCode -ne 0) 'old fill-in wording was not rejected'
        Assert-True ($result.Output -match 'fill-in') 'failure reason is not the fill-in guard'
    }
    finally {
        Remove-Sandbox $box
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host ''
if ($script:failed -gt 0) {
    Write-Host "[FAIL] $($script:failed) test(s) failed, $($script:passed) passed."
    exit 1
}

Write-Host "[OK]   $($script:passed) test(s) passed."
exit 0
