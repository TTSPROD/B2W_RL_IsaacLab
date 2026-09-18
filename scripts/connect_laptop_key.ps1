[CmdletBinding()]
param([switch]$CheckOnly)
# Run interactively on the workstation. Password is entered only into ssh.exe.
$ErrorActionPreference = 'Stop'
$WorkerAddress = '192.168.1.129'
$WorkerUser = 'severstal\ra.suragin'
$PublicPath = Join-Path $env:USERPROFILE '.ssh/id_ed25519.pub'
$PrivatePath = Join-Path $env:USERPROFILE '.ssh/id_ed25519'
$PublicParts = ([IO.File]::ReadAllText($PublicPath).Trim() -split '\s+')
if ($PublicParts.Count -lt 2 -or $PublicParts[0] -ne 'ssh-ed25519' -or $PublicParts[1] -notmatch '^[A-Za-z0-9+/=]+$') {
    throw 'Expected an existing Ed25519 public key'
}
$PublicKey = $PublicParts[0] + ' ' + $PublicParts[1] + ' b2w-workstation'
$PublicEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($PublicKey))
$RemoteScript = @'
$ErrorActionPreference = 'Stop'
$Key = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__PUBLIC_KEY__'))
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$AdminMember = @($Identity.Groups | ForEach-Object { $_.Value }) -contains 'S-1-5-32-544'
if ($AdminMember) {
    $KeyFile = Join-Path $env:ProgramData 'ssh/administrators_authorized_keys'
} else {
    $KeyDirectory = Join-Path $env:USERPROFILE '.ssh'
    New-Item -ItemType Directory -Force -Path $KeyDirectory | Out-Null
    $KeyFile = Join-Path $KeyDirectory 'authorized_keys'
}
$NoBom = New-Object Text.UTF8Encoding($false)
if (-not (Test-Path -LiteralPath $KeyFile)) {
    [IO.File]::WriteAllText($KeyFile, '', $NoBom)
}
if ($AdminMember) {
    & icacls.exe $KeyFile /inheritance:r /grant:r '*S-1-5-32-544:F' '*S-1-5-18:F'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot set administrator key-file permissions' }
}
$Existing = [IO.File]::ReadAllLines($KeyFile)
$KeyBlob = ($Key -split '\s+')[1]
$AlreadyPresent = @($Existing | Where-Object { ($_ -split '\s+') -contains $KeyBlob }).Count -gt 0
if (-not $AlreadyPresent) {
    [IO.File]::AppendAllText($KeyFile, [Environment]::NewLine + $Key + [Environment]::NewLine, $NoBom)
}
Write-Host ('Public key ready for ' + $Identity.Name + ': ' + $KeyFile)
'@
$RemoteScript = $RemoteScript.Replace('__PUBLIC_KEY__', $PublicEncoded)
$Tokens = $null
$ParseErrors = $null
[Management.Automation.Language.Parser]::ParseInput($RemoteScript, [ref]$Tokens, [ref]$ParseErrors) | Out-Null
if ($ParseErrors.Count) { throw ($ParseErrors | Out-String) }
if ($CheckOnly) {
    Write-Host "Syntax checked. Target: $WorkerUser@$WorkerAddress. No connection or changes made."
    & ssh-keygen.exe -lf $PublicPath
    exit $LASTEXITCODE
}
$EncodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($RemoteScript))
Write-Host 'Enter the laptop account password at the SSH prompt. It is not saved by this script.'
& ssh.exe -o BatchMode=no -o PreferredAuthentications=password,keyboard-interactive -o PubkeyAuthentication=no -l $WorkerUser $WorkerAddress "powershell.exe -NoProfile -EncodedCommand $EncodedCommand"
if ($LASTEXITCODE -ne 0) { throw 'SSH key installation failed; see the output above' }
& ssh.exe -o BatchMode=yes -o IdentitiesOnly=yes -i $PrivatePath -l $WorkerUser $WorkerAddress whoami
if ($LASTEXITCODE -ne 0) { throw 'Public-key login still failed; retain the output for diagnosis' }
Write-Host 'Key-based login verified. Return to Codex to continue laptop setup.'
