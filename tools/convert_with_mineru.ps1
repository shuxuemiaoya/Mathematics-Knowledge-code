param(
    [Parameter(Mandatory = $true)]
    [string]$RootDir,

    [string]$OutDir = $(if ($env:KNOWLEDGE_BASE_DIR) { $env:KNOWLEDGE_BASE_DIR } else { "C:\mygithub\Secondary-School-Mathematics-Knowledge-Map" }),

    [string]$BaseSrcDir = $(if ($env:SOURCE_MATERIALS_DIR) { $env:SOURCE_MATERIALS_DIR } else { "C:\code\BaiduSyncdisk\数学妙呀资料" }),

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

python -m math_knowledge_tools.mineru.cli $RootDir --out-dir $OutDir --base-src-dir $BaseSrcDir --format $Format
exit $LASTEXITCODE
