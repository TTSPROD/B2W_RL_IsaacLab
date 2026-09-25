[CmdletBinding()]
param([string]$DestinationRoot = '')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $DestinationRoot) {
    $codexDirectory = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
    $DestinationRoot = Join-Path $codexDirectory 'skills'
}
$names = @('isaacsim-b2w-gamepad-window', 'mujoco-b2w-gamepad-window')
foreach ($name in $names) {
    $source = Join-Path $projectRoot "skills/$name"
    foreach ($relative in @('SKILL.md', 'agents/openai.yaml')) {
        $sourceFile = Join-Path $source $relative
        if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) { throw "Missing skill file: $sourceFile" }
    }
}
foreach ($name in $names) {
    foreach ($relative in @('SKILL.md', 'agents/openai.yaml')) {
        $sourceFile = Join-Path $projectRoot "skills/$name/$relative"
        $targetFile = [IO.Path]::GetFullPath((Join-Path $DestinationRoot "$name/$relative"))
        if ($targetFile -eq [IO.Path]::GetFullPath($sourceFile)) { continue }
        New-Item -ItemType Directory -Path (Split-Path $targetFile) -Force | Out-Null
        Copy-Item -LiteralPath $sourceFile -Destination $targetFile -Force
        if ((Get-FileHash -LiteralPath $sourceFile).Hash -ne (Get-FileHash -LiteralPath $targetFile).Hash) {
            throw "Installed skill hash mismatch: $targetFile"
        }
    }
    Write-Output "Installed $name to $DestinationRoot"
}
