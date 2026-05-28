param(
    [string[]]$SkillName,
    [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }),
    [switch]$Force
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $repoRoot "skills"
$targetRoot = Join-Path $CodexHome "skills"

if (-not (Test-Path -LiteralPath $sourceRoot)) {
    throw "Skill source directory not found: $sourceRoot"
}

New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null

$skillDirs = if ($SkillName -and $SkillName.Count -gt 0) {
    foreach ($name in $SkillName) {
        $path = Join-Path $sourceRoot $name
        if (-not (Test-Path -LiteralPath $path -PathType Container)) {
            throw "Skill not found: $name"
        }
        Get-Item -LiteralPath $path
    }
} else {
    Get-ChildItem -LiteralPath $sourceRoot -Directory
}

$skillDirs | ForEach-Object {
    $target = Join-Path $targetRoot $_.Name
    if ((Test-Path -LiteralPath $target) -and -not $Force) {
        Write-Warning "Skipping existing skill '$($_.Name)'. Re-run with -Force to overwrite files."
        return
    }

    Copy-Item -LiteralPath $_.FullName -Destination $targetRoot -Recurse -Force
    Write-Host "Installed skill: $($_.Name)"
}
