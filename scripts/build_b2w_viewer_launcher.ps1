$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$cache = Join-Path $root '.cache'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$project = Join-Path $cache 'B2WViewerLauncher.csproj'
@'
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net9.0-windows</TargetFramework>
    <UseWindowsForms>true</UseWindowsForms>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <UseAppHost>true</UseAppHost>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="..\scripts\B2WViewerLauncher.cs" />
  </ItemGroup>
</Project>
'@ | Set-Content -LiteralPath $project -Encoding utf8
$env:DOTNET_CLI_HOME = Join-Path $cache 'dotnet-home'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:NUGET_PACKAGES = Join-Path $cache 'nuget'
New-Item -ItemType Directory -Force -Path $env:DOTNET_CLI_HOME | Out-Null
& dotnet build $project -c Release -o $cache
if ($LASTEXITCODE -ne 0) { throw 'B2W viewer launcher build failed' }
Write-Output (Join-Path $cache 'B2WViewerLauncher.exe')
