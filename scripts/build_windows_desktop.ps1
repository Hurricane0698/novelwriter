#Requires -Version 7.2

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$RuntimeArtifactDirectory,

    [string]$OutputDirectory = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TargetTriple = "x86_64-pc-windows-msvc"
$RequiredNodeVersion = "v20.19.5"
$RequiredRustVersion = "1.85.0"
$RequiredTauriCliVersion = "2.11.4"

function Resolve-AbsolutePath {
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [string] $BasePath
    )

    if ([IO.Path]::IsPathRooted($Path)) {
        return [IO.Path]::GetFullPath($Path)
    }
    return [IO.Path]::GetFullPath((Join-Path $BasePath $Path))
}

if ($env:OS -ne "Windows_NT") {
    throw "The NovWr desktop installer must be built on Windows."
}

$WindowsVersion = [Environment]::OSVersion.Version
if ($WindowsVersion.Major -ne 10 -or $WindowsVersion.Build -lt 22000) {
    throw "The NovWr desktop installer requires Windows 11; found $WindowsVersion."
}

$ProcessArchitecture = [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
if ($ProcessArchitecture -ne "X64") {
    throw "The NovWr desktop installer requires an x64 build process; found $ProcessArchitecture."
}

$RootDirectory = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DesktopDirectory = Join-Path $RootDirectory "desktop"
$TauriDirectory = Join-Path $DesktopDirectory "src-tauri"
$RuntimeArtifactDirectory = Resolve-AbsolutePath -Path $RuntimeArtifactDirectory -BasePath $RootDirectory
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $DesktopDirectory "desktop-dist"
} else {
    $OutputDirectory = Resolve-AbsolutePath -Path $OutputDirectory -BasePath $RootDirectory
}

if (-not (Test-Path -LiteralPath $RuntimeArtifactDirectory -PathType Container)) {
    throw "The downloaded Windows runtime artifact is missing: $RuntimeArtifactDirectory"
}

$RuntimeExecutable = Join-Path $RuntimeArtifactDirectory "novwr-runtime.exe"
$RuntimeInternalDirectory = Join-Path $RuntimeArtifactDirectory "_internal"
if (-not (Test-Path -LiteralPath $RuntimeExecutable -PathType Leaf)) {
    throw "The runtime artifact must expose novwr-runtime.exe at its root: $RuntimeExecutable"
}
if (-not (Test-Path -LiteralPath $RuntimeInternalDirectory -PathType Container)) {
    throw "The runtime artifact must expose the complete PyInstaller _internal directory: $RuntimeInternalDirectory"
}

$NodeVersion = (& node --version).Trim()
if ($LASTEXITCODE -ne 0 -or $NodeVersion -ne $RequiredNodeVersion) {
    throw "The NovWr desktop build requires Node.js $RequiredNodeVersion; found $NodeVersion."
}

$RustVersionLines = @(& rustc --version --verbose)
if ($LASTEXITCODE -ne 0) {
    throw "rustc version check failed."
}
$RustReleaseLine = $RustVersionLines | Where-Object { $_ -like "release:*" }
$RustHostLine = $RustVersionLines | Where-Object { $_ -like "host:*" }
if ($RustReleaseLine -ne "release: $RequiredRustVersion") {
    throw "The NovWr desktop build requires Rust $RequiredRustVersion; found $RustReleaseLine."
}
if ($RustHostLine -ne "host: $TargetTriple") {
    throw "The NovWr desktop build requires the $TargetTriple Rust host; found $RustHostLine."
}

$InstalledTargets = @(& rustup target list --installed)
if ($LASTEXITCODE -ne 0 -or $TargetTriple -notin $InstalledTargets) {
    throw "The required Rust target is not installed: $TargetTriple"
}

$PackageJsonPath = Join-Path $DesktopDirectory "package.json"
$PackageLockPath = Join-Path $DesktopDirectory "package-lock.json"
$CargoLockPath = Join-Path $TauriDirectory "Cargo.lock"
$NsisTemplatePath = Join-Path $TauriDirectory "nsis/installer.nsi"
foreach ($RequiredFile in @($PackageJsonPath, $PackageLockPath, $CargoLockPath, $NsisTemplatePath)) {
    if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
        throw "A locked desktop build input is missing: $RequiredFile"
    }
}

$PackageJson = Get-Content -LiteralPath $PackageJsonPath -Raw | ConvertFrom-Json -AsHashtable
$PackageLock = Get-Content -LiteralPath $PackageLockPath -Raw | ConvertFrom-Json -AsHashtable
$DeclaredTauriCliVersion = [string]$PackageJson["devDependencies"]["@tauri-apps/cli"]
$LockedTauriCliVersion = [string]$PackageLock["packages"]["node_modules/@tauri-apps/cli"]["version"]
if (
    $DeclaredTauriCliVersion -ne $RequiredTauriCliVersion -or
    $LockedTauriCliVersion -ne $RequiredTauriCliVersion
) {
    throw "The desktop manifest and lock must pin @tauri-apps/cli $RequiredTauriCliVersion exactly."
}

$ResourceDirectory = Join-Path $TauriDirectory "resources/novwr-runtime"
if (Test-Path -LiteralPath $ResourceDirectory) {
    Remove-Item -LiteralPath $ResourceDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $ResourceDirectory -Force | Out-Null
Copy-Item -Path (Join-Path $RuntimeArtifactDirectory "*") -Destination $ResourceDirectory -Recurse -Force

foreach ($RequiredRuntimePath in @("novwr-runtime.exe", "_internal")) {
    $StagedPath = Join-Path $ResourceDirectory $RequiredRuntimePath
    if (-not (Test-Path -LiteralPath $StagedPath)) {
        throw "The complete runtime onedir was not staged for Tauri: $StagedPath"
    }
}

Push-Location $DesktopDirectory
try {
    & npm ci
    if ($LASTEXITCODE -ne 0) {
        throw "npm ci failed for the locked desktop dependencies."
    }

    $TauriCli = Join-Path $DesktopDirectory "node_modules/.bin/tauri.cmd"
    if (-not (Test-Path -LiteralPath $TauriCli -PathType Leaf)) {
        throw "The locked local Tauri CLI is missing: $TauriCli"
    }
    $TauriVersion = (& $TauriCli --version).Trim()
    if ($LASTEXITCODE -ne 0 -or $TauriVersion -notmatch "(?:^| )$([regex]::Escape($RequiredTauriCliVersion))$") {
        throw "The local Tauri CLI must be $RequiredTauriCliVersion; found $TauriVersion."
    }

    & cargo metadata --locked --format-version 1 --no-deps --manifest-path (Join-Path $TauriDirectory "Cargo.toml") | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Cargo.lock does not satisfy the desktop manifest."
    }

    & cargo test --locked --target $TargetTriple --lib --manifest-path (Join-Path $TauriDirectory "Cargo.toml")
    if ($LASTEXITCODE -ne 0) {
        throw "The locked Windows desktop Rust library tests failed."
    }

    & $TauriCli build --bundles nsis --target $TargetTriple --ci -- --locked
    if ($LASTEXITCODE -ne 0) {
        throw "The locked Tauri NSIS build failed."
    }
} finally {
    Pop-Location
}

$BundleDirectory = Join-Path $TauriDirectory "target/$TargetTriple/release/bundle/nsis"
$SetupFiles = @(
    Get-ChildItem -LiteralPath $BundleDirectory -Filter "*-setup.exe" -File
)
if ($SetupFiles.Count -ne 1) {
    throw "The Tauri build must produce exactly one NSIS setup executable; found $($SetupFiles.Count)."
}

$ExpectedSetupName = "NovWr_$($PackageJson["version"])_x64-setup.exe"
if ($SetupFiles[0].Name -ne $ExpectedSetupName) {
    throw "Unexpected NSIS setup name '$($SetupFiles[0].Name)'; expected '$ExpectedSetupName'."
}

if (Test-Path -LiteralPath $OutputDirectory) {
    Remove-Item -LiteralPath $OutputDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$PublishedSetupPath = Join-Path $OutputDirectory $ExpectedSetupName
Copy-Item -LiteralPath $SetupFiles[0].FullName -Destination $PublishedSetupPath

$PublishedFiles = @(Get-ChildItem -LiteralPath $OutputDirectory -File)
if ($PublishedFiles.Count -ne 1 -or $PublishedFiles[0].FullName -ne $PublishedSetupPath) {
    throw "The desktop output directory must contain exactly one setup executable."
}

Write-Output "Windows desktop setup: $PublishedSetupPath"
