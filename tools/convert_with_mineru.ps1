param(
    [Parameter(Mandatory = $true)]
    [string]$RootDir,

    [string]$OutDir = $env:KNOWLEDGE_BASE_DIR,

    [string]$BaseSrcDir = $env:SOURCE_MATERIALS_DIR,

    [ValidateSet("none", "textbook", "exercise", "yishu", "bishua", "all_exercises")]
    [string]$Format = "none"
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$srcPath = Join-Path $repoRoot "src"
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $srcPath
}

# Fix encoding for Chinese characters in paths
$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$argsList = @($RootDir, "--format", $Format)
if ($OutDir) {
    $argsList += "--out-dir"
    $argsList += $OutDir
}
if ($BaseSrcDir) {
    $argsList += "--base-src-dir"
    $argsList += $BaseSrcDir
}

python -m math_knowledge_tools.mineru.cli @argsList
exit $LASTEXITCODE
