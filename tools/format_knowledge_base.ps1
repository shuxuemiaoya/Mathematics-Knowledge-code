param(
    [ValidateSet("none", "textbook", "exercise", "yishu", "bishua", "all_exercises", "zheda_youfu")]
    [string]$Mode = "textbook",

    [string]$Dir = $(if ($env:KNOWLEDGE_BASE_DIR) { $env:KNOWLEDGE_BASE_DIR } else { "C:\mygithub\Secondary-School-Mathematics-Knowledge-Map" }),

    [switch]$Backup,
    [switch]$DryRun
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$srcPath = Join-Path $repoRoot "src"
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $srcPath
}

$commandArgs = @(
    "-m", "mathos.formatter.cli",
    "--dir", $Dir,
    "--mode", $Mode
)

if ($Backup) {
    $commandArgs += "--backup"
}

if ($DryRun) {
    $commandArgs += "--dry-run"
}

python @commandArgs
exit $LASTEXITCODE
