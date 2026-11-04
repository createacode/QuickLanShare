#requires -Version 5.1
<#
.SYNOPSIS
    Validate the repository: generated templates, headings, cross references,
    placeholders, guide step numbering, local links and required files.

.DESCRIPTION
    Run this before committing. It exits with code 1 when any check fails.
    The check is dependency-free so it works on a clean Windows box.
    This file is ASCII-only on purpose: Windows PowerShell 5.1 reads
    BOM-less scripts with the ANSI code page.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/check-templates.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$script:fail = 0
$script:warn = 0

function Fail([string]$Message) {
    Write-Host "[FAIL] $Message"
    $script:fail++
}

function Warn([string]$Message) {
    Write-Host "[WARN] $Message"
    $script:warn++
}

function Ok([string]$Message) {
    Write-Host "[OK]   $Message"
}

function Read-Utf8([string]$Path) {
    return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
}

# ---------------------------------------------------------------------------
# 1. docs/<language>/template.md must match parts/
# ---------------------------------------------------------------------------
try {
    & (Join-Path $PSScriptRoot 'build-templates.ps1') -Check
    if ($LASTEXITCODE -ne 0) {
        $script:fail++
    }
}
catch {
    Fail "build-templates.ps1 failed: $_"
}

# ---------------------------------------------------------------------------
# 2. Template structure and content rules
# ---------------------------------------------------------------------------
$templateFiles = @(
    'docs/cpp/template.md',
    'docs/python/template.md',
    'docs/java/template.md',
    'docs/rust/template.md',
    'docs/android/template.md',
    'docs/vue/template.md'
)
$requiredIds = @('V0', 'V1', 'V2') + (0..11 | ForEach-Object { "L$_" })
$allowedPlaceholders = @('AUTHOR', 'YYYY.M', 'SOFTWARE_NAME', 'VERSION')

foreach ($relative in $templateFiles) {
    $path = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $path)) {
        Fail "Missing template: $relative"
        continue
    }

    $bytes = [System.IO.File]::ReadAllBytes($path)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        Fail "$relative starts with a UTF-8 BOM"
    }

    $text = Read-Utf8 $path

    if (-not $text.EndsWith("`n")) {
        Fail "$relative does not end with a newline"
    }

    if ($text -match '(?m)^\s*@@include') {
        Fail "$relative contains an unresolved @@include directive"
    }

    $headingIds = @()
    foreach ($match in [regex]::Matches($text, '(?m)^#{2,4}\s+((?:L|V)\d+(?:\.\d+)?)\b')) {
        $headingIds += $match.Groups[1].Value
    }

    foreach ($id in $requiredIds) {
        if ($headingIds -notcontains $id) {
            Fail "$relative is missing heading $id"
        }
    }

    $body = [regex]::Replace($text, '(?m)^#{2,4}\s+.*$', '')
    $references = @(
        [regex]::Matches($body, '(?<![A-Za-z0-9_])L(\d+(?:\.\d+)?)(?![\d.])') |
            ForEach-Object { "L$($_.Groups[1].Value)" } |
            Sort-Object -Unique
    )
    foreach ($reference in $references) {
        if ($headingIds -notcontains $reference) {
            Fail "$relative references a missing section: $reference"
        }
    }

    $placeholders = @(
        [regex]::Matches($text, '\{\{([A-Za-z0-9_.]+)\}\}') |
            ForEach-Object { $_.Groups[1].Value } |
            Sort-Object -Unique
    )
    foreach ($placeholder in $placeholders) {
        if ($allowedPlaceholders -notcontains $placeholder) {
            Fail "$relative uses an unknown placeholder: {{$placeholder}}"
        }
    }

    # Conversation-first protocol: natural-language input, a requirement digest,
    # and a no-requirements branch. Unicode escapes keep this script ASCII-only.
    $protocolPhrases = [ordered]@{
        'natural-language input'    = '\u81EA\u7136\u8BED\u8A00'
        'requirement digest'        = '\u9700\u6C42\u7406\u89E3'
        'no-requirements branch'    = '\u6CA1\u6709\u9700\u6C42'
    }
    foreach ($name in $protocolPhrases.Keys) {
        if ($text -notmatch $protocolPhrases[$name]) {
            Fail "$relative is missing the conversation-first protocol: $name"
        }
    }

    if ($text -match '\u53EA\u586B\u5199|\u53EA\u586B\u8FD9\u4E00\u8282|\u9700\u8981\u586B\u5199\u6216\u786E\u8BA4') {
        Fail "$relative still contains the old fill-in-the-form wording"
    }

    if ($text -notmatch '\u9762\u5411\u4F7F\u7528\u8005') {
        Fail "$relative is missing the user-facing README rule"
    }

    if ($text -notmatch 'docs/develop-readme\.md') {
        Fail "$relative is missing docs/develop-readme.md"
    }

    if ($text -match '2026\.9') {
        Fail "$relative still contains the stale year-month 2026.9"
    }

    if ($text -match 'Copyright[^\r\n]*?\b20\d\d\.\d') {
        Fail "$relative hard-codes a copyright year-month"
    }

    $checklistCount = ([regex]::Matches($text, '(?m)^- \[ \]')).Count
    if ($checklistCount -lt 20) {
        Fail "$relative has only $checklistCount checklist items (expected at least 20)"
    }

    $trailing = ([regex]::Matches($text, '(?m)[ \t]+$')).Count
    if ($trailing -gt 0) {
        Warn "$relative has $trailing line(s) with trailing whitespace"
    }

    $longLines = @($text -split "`n" | Where-Object { $_.Length -gt 260 }).Count
    if ($longLines -gt 0) {
        Warn "$relative has $longLines line(s) longer than 260 characters"
    }

    Ok "$relative structure is valid"
}

# ---------------------------------------------------------------------------
# 3. Language / delivery markers required by the product requirements
# ---------------------------------------------------------------------------
$templateMarkers = [ordered]@{
    'docs/java/template.md' = @('Java 17', 'jar', 'centos-run.md', 'MySQL 8.0+')
    'docs/rust/template.md' = @('Cargo', 'exe')
    'docs/android/template.md' = @('Kotlin', 'apk', 'minSdk = 29', 'MySQL 8.0+')
    'docs/vue/template.md' = @('npm run serve', 'npm run build', 'nginx')
}

foreach ($relative in $templateMarkers.Keys) {
    $path = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $path)) {
        Fail "Missing template: $relative"
        continue
    }
    $text = Read-Utf8 $path
    foreach ($marker in $templateMarkers[$relative]) {
        if ($text -notmatch [regex]::Escape($marker)) {
            Fail "$relative is missing required marker: $marker"
        }
    }
    Ok "$relative contains its delivery markers"
}

# MySQL is only allowed for Java (backend) and Android (via the Java API).
$noDbTemplates = @(
    'docs/cpp/template.md',
    'docs/python/template.md',
    'docs/rust/template.md',
    'docs/vue/template.md'
)
foreach ($relative in $noDbTemplates) {
    $path = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $path)) {
        Fail "Missing template: $relative"
        continue
    }
    $text = Read-Utf8 $path
    if ($text -match 'MySQL|mysql|sqlx') {
        Fail "$relative must not mention MySQL or sqlx"
    }
    else {
        Ok "$relative has no MySQL/sqlx dependency"
    }
}

# UI-bearing templates must carry the modern, clean design requirement.
$uiTemplates = @(
    'docs/cpp/template.md',
    'docs/python/template.md',
    'docs/android/template.md',
    'docs/vue/template.md'
)
foreach ($relative in $uiTemplates) {
    $path = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $path)) {
        Fail "Missing template: $relative"
        continue
    }
    $text = Read-Utf8 $path
    if ($text -notmatch '\u73B0\u4EE3\u5316\u8BBE\u8BA1\u98CE\u683C' -or
        $text -notmatch '\u7B80\u6D01\u5927\u6C14' -or
        $text -notmatch '\u6838\u5FC3\u529F\u80FD\u64CD\u4F5C\u533A\u57DF' -or
        $text -notmatch '\u9AA8\u67B6' -or
        $text -notmatch '\u8FC7\u6E21') {
        Fail "$relative is missing the modern UI / skeleton loading requirement"
    }
    else {
        Ok "$relative contains the modern UI / skeleton loading requirement"
    }
}

$vueTemplate = Join-Path $root 'docs/vue/template.md'
if (Test-Path -LiteralPath $vueTemplate) {
    if ((Read-Utf8 $vueTemplate) -notmatch '\u4E0D\u6267\u884C') {
        Fail 'docs/vue/template.md does not state that AI must not run npm commands'
    }
    else {
        Ok 'docs/vue/template.md states that AI must not run npm commands'
    }
}

# ---------------------------------------------------------------------------
# 3. Android guide: no dead references, TOC step labels must match headings
#    U+7B2C = step, U+6B65 = counter word; kept escaped to stay ASCII-only.
# ---------------------------------------------------------------------------
$guidePath = Join-Path $root 'docs/android/environment.md'
if (-not (Test-Path -LiteralPath $guidePath)) {
    Fail 'Missing guide: docs/android/environment.md'
}
else {
    $guide = Read-Utf8 $guidePath

    if ($guide -match 'test\\set-user-path') {
        Fail 'docs/android/environment.md references the removed script test\set-user-path.cmd'
    }
    if ($guide -match 'test\\verify-android-env') {
        Fail 'docs/android/environment.md references the removed script test\verify-android-env.cmd'
    }
    if ($guide -match '(?m)setx\s+\w+\s+""') {
        Fail 'docs/android/environment.md still documents setx VAR with an empty value'
    }

    $headingSteps = @(
        [regex]::Matches($guide, '(?m)^##\s+\u7B2C(.+?)\u6B65') |
            ForEach-Object { $_.Groups[1].Value }
    )
    $tableSteps = @(
        [regex]::Matches($guide, '(?m)^\|\s*\u7B2C(.+?)\u6B65\s*\|') |
            ForEach-Object { $_.Groups[1].Value }
    )

    if ($headingSteps.Count -eq 0) {
        Fail 'docs/android/environment.md has no step headings'
    }
    elseif (($headingSteps -join ',') -ne ($tableSteps -join ',')) {
        Fail ("Step overview [$($tableSteps -join ',')] does not match headings [$($headingSteps -join ',')]")
    }
    else {
        Ok "docs/android/environment.md has $($headingSteps.Count) steps, TOC matches headings"
    }
}

# ---------------------------------------------------------------------------
# 4. Local markdown links must resolve
# ---------------------------------------------------------------------------
$docFiles = @(
    'readme.md',
    'AGENTS.md',
    'docs/readme.md',
    'docs/develop-readme.md',
    'docs/license.md',
    'docs/android/environment.md',
    'docs/examples/conversation.md'
)

foreach ($relative in $docFiles) {
    $path = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $path)) {
        Fail "Missing document: $relative"
        continue
    }

    $directory = Split-Path -Parent $path
    $text = Read-Utf8 $path
    $broken = 0

    foreach ($match in [regex]::Matches($text, '\]\(\s*<?([^)>\s]+)>?\s*\)')) {
        $target = $match.Groups[1].Value
        if ($target -match '^(https?:|mailto:|#)') {
            continue
        }
        $target = $target.Split('#')[0]
        if ([string]::IsNullOrWhiteSpace($target)) {
            continue
        }
        $full = Join-Path $directory $target
        if (-not (Test-Path -LiteralPath $full)) {
            Fail "$relative has a broken link: $target"
            $broken++
        }
    }

    if ($broken -eq 0) {
        Ok "$relative local links resolve"
    }
}

# ---------------------------------------------------------------------------
# 5. Required files, and no unexpected markdown at the repository root
# ---------------------------------------------------------------------------
$requiredFiles = @(
    'AGENTS.md',
    'readme.md',
    'LICENSE',
    '.gitignore',
    '.gitattributes',
    'docs/readme.md',
    'docs/develop-readme.md',
    'docs/license.md',
    'docs/cpp/template.md',
    'docs/python/template.md',
    'docs/java/template.md',
    'docs/rust/template.md',
    'docs/android/template.md',
    'docs/vue/template.md',
    'parts/cpp.md',
    'parts/python.md',
    'parts/java.md',
    'parts/rust.md',
    'parts/android.md',
    'parts/vue.md',
    'docs/android/environment.md',
    'docs/examples/conversation.md',
    'cache/screenshots/.gitkeep',
    'cache/images/.gitkeep',
    'cache/diagrams/.gitkeep',
    'cache/videos/.gitkeep',
    'tests/run-tests.ps1',
    'scripts/build-templates.ps1',
    'scripts/check-templates.ps1'
)

foreach ($relative in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $relative))) {
        Fail "Missing required file: $relative"
    }
}

$allowedRootMarkdown = @('readme.md', 'AGENTS.md')
foreach ($file in Get-ChildItem -LiteralPath $root -File -Filter '*.md') {
    if ($allowedRootMarkdown -notcontains $file.Name) {
        Warn "Unexpected markdown file at repository root: $($file.Name)"
    }
}

$legacyPaths = @(
    'templates',
    'guides',
    'examples',
    'CHANGELOG.md',
    'LICENSE-SCOPE.md',
    'docs/develop_readme.md'
)
foreach ($relative in $legacyPaths) {
    if (Test-Path -LiteralPath (Join-Path $root $relative)) {
        Fail "Legacy path still exists: $relative"
    }
}

# ---------------------------------------------------------------------------
# 6. Conversation-first documentation
# ---------------------------------------------------------------------------
$readmePath = Join-Path $root 'readme.md'
if (Test-Path -LiteralPath $readmePath) {
    $readme = Read-Utf8 $readmePath
    if ($readme -match '\u53EA\u586B\u5199|\u9700\u8981\u586B\u5199') {
        Fail 'readme.md still asks users to fill in the requirement area'
    }
    if ($readme -notmatch '\u81EA\u7136\u8BED\u8A00') {
        Fail 'readme.md does not describe natural-language requirements'
    }
    elseif ($readme -notmatch '\u9762\u5411\u4F7F\u7528\u8005') {
        Fail 'readme.md does not state that it is user-facing'
    }
    else {
        Ok 'readme.md describes the conversation-first workflow and user-facing role'
    }
}

$developerDocs = @('docs/readme.md', 'docs/develop-readme.md')
foreach ($relative in $developerDocs) {
    $path = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $path)) {
        Fail "Missing developer document: $relative"
        continue
    }
    $text = Read-Utf8 $path
    if ($text -notmatch '\u5F00\u53D1\u8005') {
        Fail "$relative does not address developers"
    }
    else {
        Ok "$relative addresses developers"
    }
}

$scriptFiles = @(
    'scripts/build-templates.ps1',
    'scripts/check-templates.ps1',
    'tests/run-tests.ps1'
)
foreach ($relative in $scriptFiles) {
    $path = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $path)) {
        Fail "Missing script: $relative"
        continue
    }
    $bytes = [System.IO.File]::ReadAllBytes($path)
    $nonAscii = @($bytes | Where-Object { $_ -gt 127 }).Count
    if ($nonAscii -gt 0) {
        Fail "$relative is not ASCII-only (found $nonAscii non-ASCII bytes)"
    }
    else {
        Ok "$relative is ASCII-only"
    }
}

$examplePath = Join-Path $root 'docs/examples/conversation.md'
if (-not (Test-Path -LiteralPath $examplePath)) {
    Fail 'Missing conversation example: docs/examples/conversation.md'
}
else {
    $example = Read-Utf8 $examplePath
    if ($example -notmatch '\u9700\u6C42\u7406\u89E3') {
        Fail 'docs/examples/conversation.md does not show a requirement digest'
    }
    else {
        Ok 'conversation example shows natural language and a requirement digest'
    }
}

# ---------------------------------------------------------------------------
# 7. AI navigation and cache layout
# ---------------------------------------------------------------------------
$agentsPath = Join-Path $root 'AGENTS.md'
if (-not (Test-Path -LiteralPath $agentsPath)) {
    Fail 'Missing AGENTS.md'
}
else {
    $agents = Read-Utf8 $agentsPath
    foreach ($language in @('C++', 'Python', 'Java', 'Rust', 'Android', 'Vue')) {
        if ($agents -notmatch [regex]::Escape($language)) {
            Fail "AGENTS.md does not mention $language"
        }
    }
    if ($agents -notmatch 'docs/' -or $agents -notmatch 'cache/') {
        Fail 'AGENTS.md does not explain the docs/ and cache/ layout'
    }
    else {
        Ok 'AGENTS.md covers six languages and the docs/cache layout'
    }
}

$cacheDirs = @(
    'cache/screenshots',
    'cache/images',
    'cache/diagrams',
    'cache/videos'
)
foreach ($relative in $cacheDirs) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $relative))) {
        Fail "Missing cache directory: $relative"
    }
}

$cacheRoot = Join-Path $root 'cache'
if (Test-Path -LiteralPath $cacheRoot) {
    $looseFiles = @(Get-ChildItem -LiteralPath $cacheRoot -File -Force)
    if ($looseFiles.Count -gt 0) {
        Fail "cache/ root contains loose files; move them into a type subdirectory"
    }
    else {
        Ok 'cache/ resources are grouped in type subdirectories'
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host ''
if ($script:fail -gt 0) {
    Write-Host "[FAIL] $($script:fail) check(s) failed, $($script:warn) warning(s)."
    exit 1
}

Write-Host "[OK]   All checks passed ($($script:warn) warning(s))."
