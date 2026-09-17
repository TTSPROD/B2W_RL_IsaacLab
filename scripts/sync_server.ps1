<#
.SYNOPSIS
Synchronize the committed HEAD to the project's dedicated training-server checkout.
.DESCRIPTION
Uses a complete Git bundle and SCP; the server never connects to GitHub.
The destination is fixed to user@10.126.161.7:/home/user/projects/B2W_RL_IsaacLab.
Existing checkouts must have the expected origin, matching branch, and a clean
working tree (including untracked files; ignored caches are permitted).
Updates are fast-forward only. Nothing is reset, removed, or searched outside
the explicitly named checkout and transfer-cache directories.

Local transfer artifacts: .cache/server-sync/
Remote transfer artifacts: /home/user/.cache/B2W_RL_IsaacLab-sync/
Artifacts are retained for inspection, including after a failed transfer.
.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts/sync_server.ps1 -DryRun
.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts/sync_server.ps1
.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts/sync_server.ps1 -AllowPasswordPrompt
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$AllowPasswordPrompt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RemoteLogin = 'user@10.126.161.7'
$RemoteTarget = '/home/user/projects/B2W_RL_IsaacLab'
$RemoteCache = '/home/user/.cache/B2W_RL_IsaacLab-sync'
$CanonicalOrigin = 'https://github.com/TTSPROD/B2W_RL_IsaacLab.git'
$AllowedOrigins = @(
    'https://github.com/TTSPROD/B2W_RL_IsaacLab.git',
    'https://github.com/TTSPROD/B2W_RL_IsaacLab',
    'git@github.com:TTSPROD/B2W_RL_IsaacLab.git',
    'git@github.com:TTSPROD/B2W_RL_IsaacLab',
    'ssh://git@github.com/TTSPROD/B2W_RL_IsaacLab.git',
    'ssh://git@github.com/TTSPROD/B2W_RL_IsaacLab'
)

$GitExe = (Get-Command git -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$SshExe = (Get-Command ssh -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$ScpExe = (Get-Command scp -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

function Get-ProjectGitOutput {
    param([Parameter(Mandatory = $true)][string[]]$GitArguments)
    $GitOutput = @(& $GitExe -C $RepoRoot @GitArguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed (exit $LASTEXITCODE): $($GitArguments -join ' ')"
    }
    return $GitOutput
}

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$NativeArguments
    )
    & $Executable @NativeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $Executable"
    }
}

function Assert-LocalCacheDirectory {
    param([Parameter(Mandatory = $true)][string]$DirectoryPath)
    $FullCachePath = [System.IO.Path]::GetFullPath($DirectoryPath)
    $RootPrefix = $RepoRoot.TrimEnd([char[]]@('\', '/')) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $FullCachePath.StartsWith($RootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Transfer cache is outside the project: $FullCachePath"
    }
    if (Test-Path -LiteralPath $FullCachePath) {
        $CacheItem = Get-Item -LiteralPath $FullCachePath -Force
        if (-not $CacheItem.PSIsContainer) {
            throw "Transfer cache path is not a directory: $FullCachePath"
        }
        if (($CacheItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Transfer cache must not be a symlink or junction: $FullCachePath"
        }
    }
}

$GitTopLevel = [string](Get-ProjectGitOutput -GitArguments @('rev-parse', '--show-toplevel'))
$GitTopLevel = [System.IO.Path]::GetFullPath($GitTopLevel)
if (-not $GitTopLevel.Equals($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The script must reside in the scripts directory of the project repository.'
}

$OriginValues = @(Get-ProjectGitOutput -GitArguments @('config', '--get-all', 'remote.origin.url'))
if ($OriginValues.Count -ne 1 -or $AllowedOrigins -cnotcontains $OriginValues[0]) {
    throw 'Local origin must identify exactly TTSPROD/B2W_RL_IsaacLab on github.com.'
}

$HeadCommit = [string](Get-ProjectGitOutput -GitArguments @('rev-parse', '--verify', 'HEAD^{commit}'))
if ($HeadCommit -notmatch '\A[0-9a-f]{40}\z') {
    throw 'Expected a committed SHA-1 Git HEAD; commit the project before synchronizing.'
}
$SourceBranch = [string](Get-ProjectGitOutput -GitArguments @('symbolic-ref', '--quiet', '--short', 'HEAD'))
# A conservative subset also makes substitution into the fixed Bash template safe.
if ($SourceBranch -notmatch '\A[A-Za-z0-9][A-Za-z0-9._/-]*\z') {
    throw 'The checked-out branch name is unsupported; use a simple named branch.'
}
$null = Get-ProjectGitOutput -GitArguments @('check-ref-format', '--branch', $SourceBranch)

$LocalChanges = @(Get-ProjectGitOutput -GitArguments @('status', '--porcelain=v1', '--untracked-files=all'))
if ($LocalChanges.Count -gt 0) {
    throw 'Local tracked or untracked changes exist. Commit the intended files before synchronizing HEAD. Ignored caches are permitted.'
}

Write-Host "Source: $RepoRoot"
Write-Host "Branch: $SourceBranch"
Write-Host "Commit: $HeadCommit"
Write-Host "Target: ${RemoteLogin}:$RemoteTarget"
if ($DryRun) {
    Write-Host 'Dry run: local validation passed. No files, SSH sessions, or remote writes were created.'
    Write-Host 'The live run will verify remote paths, upload a SHA256-checked bundle, and clone or fast-forward the clean matching checkout.'
    return
}

$CacheRoot = Join-Path $RepoRoot '.cache'
$TransferDirectory = Join-Path $CacheRoot 'server-sync'
Assert-LocalCacheDirectory -DirectoryPath $CacheRoot
Assert-LocalCacheDirectory -DirectoryPath $TransferDirectory
$null = New-Item -ItemType Directory -Path $TransferDirectory -Force

$TransferId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ') + '-' + [guid]::NewGuid().ToString('N')
$BundleName = "b2w-sync-$TransferId.bundle"
$ScriptName = "b2w-sync-$TransferId.sh"
$BundlePath = Join-Path $TransferDirectory $BundleName
$ScriptPath = Join-Path $TransferDirectory $ScriptName

# Include HEAD and its branch ref so a first clone has a normal named branch.
# Both refs were resolved above; verify them again before any remote operation.
Invoke-CheckedNative -Executable $GitExe -NativeArguments @(
    '-C', $RepoRoot, 'bundle', 'create', $BundlePath, 'HEAD', "refs/heads/$SourceBranch"
)
Invoke-CheckedNative -Executable $GitExe -NativeArguments @('-C', $RepoRoot, 'bundle', 'verify', $BundlePath)
$BundleHeads = @(Get-ProjectGitOutput -GitArguments @('bundle', 'list-heads', $BundlePath))
if ($BundleHeads -cnotcontains "$HeadCommit HEAD" -or
    $BundleHeads -cnotcontains "$HeadCommit refs/heads/$SourceBranch") {
    throw 'HEAD or the source branch moved during bundle creation. Nothing was sent to the server.'
}
$BundleSha256 = (Get-FileHash -LiteralPath $BundlePath -Algorithm SHA256).Hash.ToLowerInvariant()

# Literal here-strings: no local expansion of shell variables or command substitution.
$BootstrapCommand = @'
set -eu
command -v bash >/dev/null
command -v git >/dev/null
command -v realpath >/dev/null
command -v sha256sum >/dev/null
command -v flock >/dev/null
test $(id -un) = user
test $(realpath -m -- /home/user/projects/B2W_RL_IsaacLab) = /home/user/projects/B2W_RL_IsaacLab
test $(realpath -m -- /home/user/.cache/B2W_RL_IsaacLab-sync) = /home/user/.cache/B2W_RL_IsaacLab-sync
mkdir -p -- /home/user/projects /home/user/.cache/B2W_RL_IsaacLab-sync
'@

$RemoteScript = @'
#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly TARGET='/home/user/projects/B2W_RL_IsaacLab'
readonly CACHE='/home/user/.cache/B2W_RL_IsaacLab-sync'
readonly EXPECTED_ORIGIN='https://github.com/TTSPROD/B2W_RL_IsaacLab.git'
readonly BRANCH='@@BRANCH@@'
readonly COMMIT='@@COMMIT@@'
readonly BUNDLE_SHA256='@@SHA256@@'
readonly BUNDLE="$CACHE/@@BUNDLE@@"

fail() { printf 'Sync refused: %s\n' "$*" >&2; exit 1; }

[[ "$(id -un)" == user ]] || fail 'Unexpected server account.'
[[ "$(realpath -m -- "$TARGET")" == "$TARGET" ]] || fail 'Target or a parent resolves through a symlink.'
[[ "$(realpath -m -- "$CACHE")" == "$CACHE" ]] || fail 'Transfer cache resolves outside its fixed path.'
[[ -d "$CACHE" && ! -L "$CACHE" ]] || fail 'Transfer cache is missing or a symlink.'
[[ -f "$BUNDLE" && ! -L "$BUNDLE" ]] || fail 'Bundle is missing or a symlink.'
[[ "$(realpath -- "$BUNDLE")" == "$BUNDLE" ]] || fail 'Bundle path is outside the transfer cache.'
[[ ! -L "$CACHE/sync.lock" ]] || fail 'Transfer lock must not be a symlink.'
exec 9>"$CACHE/sync.lock"
flock -n 9 || fail 'Another synchronization is active.'

ACTUAL_SHA256=$(sha256sum -- "$BUNDLE")
ACTUAL_SHA256=${ACTUAL_SHA256%% *}
[[ "$ACTUAL_SHA256" == "$BUNDLE_SHA256" ]] || fail 'Bundle SHA256 does not match.'
[[ "$(git bundle list-heads "$BUNDLE" HEAD)" == "$COMMIT HEAD" ]] || fail 'Bundle HEAD does not match.'
[[ "$(git bundle list-heads "$BUNDLE" "refs/heads/$BRANCH")" == "$COMMIT refs/heads/$BRANCH" ]] || fail 'Bundle branch does not match.'

if [[ -e "$TARGET" || -L "$TARGET" ]]; then
    [[ -d "$TARGET" && ! -L "$TARGET" ]] || fail 'Existing target is not a normal directory.'
    [[ -d "$TARGET/.git" && ! -L "$TARGET/.git" ]] || fail 'Existing target is not an independent Git checkout.'
    [[ "$(git -C "$TARGET" rev-parse --show-toplevel)" == "$TARGET" ]] || fail 'Unexpected repository root.'
    ORIGIN=$(git -C "$TARGET" config --get-all remote.origin.url) || fail 'Existing checkout has no origin.'
    case "$ORIGIN" in
        'https://github.com/TTSPROD/B2W_RL_IsaacLab.git'|'https://github.com/TTSPROD/B2W_RL_IsaacLab'|\
        'git@github.com:TTSPROD/B2W_RL_IsaacLab.git'|'git@github.com:TTSPROD/B2W_RL_IsaacLab'|\
        'ssh://git@github.com/TTSPROD/B2W_RL_IsaacLab.git'|'ssh://git@github.com/TTSPROD/B2W_RL_IsaacLab') ;;
        *) fail 'Existing origin does not identify TTSPROD/B2W_RL_IsaacLab.' ;;
    esac
    CURRENT_BRANCH=$(git -C "$TARGET" symbolic-ref --quiet --short HEAD) || fail 'Existing checkout has detached HEAD.'
    [[ "$CURRENT_BRANCH" == "$BRANCH" ]] || fail 'Existing checkout is on a different branch.'
    for state in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-apply rebase-merge sequencer index.lock HEAD.lock; do
        [[ ! -e "$TARGET/.git/$state" ]] || fail "Existing Git operation or lock: $state"
    done
    [[ -z "$(git -C "$TARGET" status --porcelain=v1 --untracked-files=all)" ]] || fail 'Existing checkout has tracked or untracked changes.'
    CURRENT_COMMIT=$(git -C "$TARGET" rev-parse --verify HEAD)
    git -C "$TARGET" bundle verify "$BUNDLE"
    git -C "$TARGET" fetch --no-tags "$BUNDLE" "refs/heads/$BRANCH"
    git -C "$TARGET" merge-base --is-ancestor "$CURRENT_COMMIT" "$COMMIT" || fail 'Update is not a fast-forward; existing work was preserved.'
    [[ "$(git -C "$TARGET" rev-parse HEAD)" == "$CURRENT_COMMIT" ]] || fail 'Existing HEAD changed during synchronization.'
    [[ "$(git -C "$TARGET" symbolic-ref --quiet --short HEAD)" == "$BRANCH" ]] || fail 'Existing branch changed during synchronization.'
    [[ -z "$(git -C "$TARGET" status --porcelain=v1 --untracked-files=all)" ]] || fail 'Existing checkout changed during synchronization.'
    git -C "$TARGET" merge --ff-only --no-edit --no-overwrite-ignore "$COMMIT"
else
    # Clone only into the exact absent destination; a partial prior checkout is
    # intentionally not overwritten or cleaned up automatically.
    git clone --branch "$BRANCH" --origin origin "$BUNDLE" "$TARGET"
    git -C "$TARGET" remote set-url origin "$EXPECTED_ORIGIN"
fi

[[ "$(git -C "$TARGET" rev-parse HEAD)" == "$COMMIT" ]] || fail 'Final HEAD verification failed.'
[[ "$(git -C "$TARGET" symbolic-ref --quiet --short HEAD)" == "$BRANCH" ]] || fail 'Final branch verification failed.'
[[ -z "$(git -C "$TARGET" status --porcelain=v1 --untracked-files=all)" ]] || fail 'Final checkout is not clean.'
printf 'Synchronized %s at %s (%s)\n' "$TARGET" "$COMMIT" "$BRANCH"
printf 'Transfer artifacts retained in %s\n' "$CACHE"
'@

$RemoteScript = $RemoteScript.Replace('@@BRANCH@@', $SourceBranch).
    Replace('@@COMMIT@@', $HeadCommit).
    Replace('@@SHA256@@', $BundleSha256).
    Replace('@@BUNDLE@@', $BundleName)
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ScriptPath, $RemoteScript.Replace("`r`n", "`n") + "`n", $Utf8NoBom)
$BootstrapCommand = $BootstrapCommand.Replace("`r`n", "`n")

$SshOptions = @('-o', 'ConnectTimeout=15')
if (-not $AllowPasswordPrompt) {
    $SshOptions += @('-o', 'BatchMode=yes')
}
# Host-key verification retains the user's normal OpenSSH policy. No insecure
# host-key, TLS, or DNS overrides are introduced by this synchronization script.
Invoke-CheckedNative -Executable $SshExe -NativeArguments ($SshOptions + @($RemoteLogin, $BootstrapCommand))
Invoke-CheckedNative -Executable $ScpExe -NativeArguments ($SshOptions + @(
    $BundlePath, $ScriptPath, "${RemoteLogin}:$RemoteCache/"
))

# The remote command includes only the fixed directory and generated safe name.
$RunRemoteScript = "bash -- '$RemoteCache/$ScriptName'"
Invoke-CheckedNative -Executable $SshExe -NativeArguments ($SshOptions + @($RemoteLogin, $RunRemoteScript))
Write-Host "Synchronization complete: $HeadCommit"
Write-Host "Local transfer artifacts: $TransferDirectory"
