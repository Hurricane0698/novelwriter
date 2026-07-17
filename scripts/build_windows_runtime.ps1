#Requires -Version 7.2

[CmdletBinding()]
param(
    [string]$OutputDirectory = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "The NovWr desktop runtime must be built on Windows."
}

$ProcessArchitecture = [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
if ($ProcessArchitecture -ne "X64") {
    throw "The NovWr desktop runtime requires an x64 build process; found $ProcessArchitecture."
}

$RootDirectory = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $RootDirectory "desktop/runtime-dist"
} elseif (-not [IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Path $RootDirectory $OutputDirectory
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$WorkDirectory = Join-Path $RootDirectory "desktop/build/pyinstaller"
$SpecPath = Join-Path $RootDirectory "desktop/runtime/novwr-runtime.spec"
$RequiredUvVersion = (Get-Content -LiteralPath (Join-Path $RootDirectory ".uv-version") -Raw).Trim()
$ActualUvVersion = (& uv --version).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "uv version check failed."
}
if ($ActualUvVersion -ne "uv $RequiredUvVersion") {
    throw "NovWr requires uv $RequiredUvVersion; found $ActualUvVersion."
}

$NodeVersion = (& node --version).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Node.js version check failed."
}
if ($NodeVersion -notmatch '^v20\.') {
    throw "The NovWr desktop runtime requires Node.js 20; found $NodeVersion."
}

$PreviousPythonUtf8 = [Environment]::GetEnvironmentVariable("PYTHONUTF8", "Process")
$PreviousUvProjectEnvironment = [Environment]::GetEnvironmentVariable("UV_PROJECT_ENVIRONMENT", "Process")
$PreviousViteApiUrl = [Environment]::GetEnvironmentVariable("VITE_API_URL", "Process")
$PreviousViteDeployMode = [Environment]::GetEnvironmentVariable("VITE_DEPLOY_MODE", "Process")

Push-Location $RootDirectory
try {
    $env:PYTHONUTF8 = "1"
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $RootDirectory ".venv"

    & uv sync --frozen --no-dev --group desktop-build
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed."
    }

    $PythonInfoJson = & uv run --no-sync python -c 'import json, platform, struct, sys; print(json.dumps({"major": sys.version_info.major, "minor": sys.version_info.minor, "machine": platform.machine(), "pointer_bits": struct.calcsize("P") * 8}))'
    if ($LASTEXITCODE -ne 0) {
        throw "Python build contract check failed."
    }
    $PythonInfo = $PythonInfoJson | ConvertFrom-Json
    if ($PythonInfo.major -ne 3 -or $PythonInfo.minor -ne 13) {
        throw "The NovWr desktop runtime requires Python 3.13; found $($PythonInfo.major).$($PythonInfo.minor)."
    }
    if ($PythonInfo.pointer_bits -ne 64 -or $PythonInfo.machine -notin @("AMD64", "x86_64")) {
        throw "The NovWr desktop runtime requires x64 Python; found $($PythonInfo.machine) with $($PythonInfo.pointer_bits)-bit pointers."
    }

    Push-Location (Join-Path $RootDirectory "web")
    try {
        & npm ci
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci failed."
        }
        $env:VITE_API_URL = ""
        $env:VITE_DEPLOY_MODE = "selfhost"
        & npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend build failed."
        }
    } finally {
        Pop-Location
    }

    & uv run --no-sync maturin develop --locked --manifest-path rust/state_proto/Cargo.toml --release
    if ($LASTEXITCODE -ne 0) {
        throw "State-proto extension build failed."
    }
    & uv run --no-sync python -c "import _novwr_state_proto; print(_novwr_state_proto.payload_format_version())"
    if ($LASTEXITCODE -ne 0) {
        throw "State-proto extension import verification failed."
    }

    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    New-Item -ItemType Directory -Force -Path $WorkDirectory | Out-Null
    & uv run --no-sync pyinstaller `
        --noconfirm `
        --clean `
        --distpath $OutputDirectory `
        --workpath $WorkDirectory `
        $SpecPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }

    $RuntimeDirectory = Join-Path $OutputDirectory "novwr-runtime"
    $RuntimeExecutable = Join-Path $RuntimeDirectory "novwr-runtime.exe"
    $InternalDirectory = Join-Path $RuntimeDirectory "_internal"
    if (-not (Test-Path -LiteralPath $RuntimeExecutable -PathType Leaf)) {
        throw "Packaged runtime executable is missing: $RuntimeExecutable"
    }

    $StateProtoModules = @(
        Get-ChildItem -Path (Join-Path $InternalDirectory "_novwr_state_proto*.pyd") -File
    )
    if ($StateProtoModules.Count -ne 1) {
        throw "Packaged runtime must contain exactly one _novwr_state_proto extension; found $($StateProtoModules.Count)."
    }

    foreach ($RelativePath in @("alembic.ini", "static/index.html")) {
        $RequiredFile = Join-Path $InternalDirectory $RelativePath
        if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
            throw "Packaged runtime resource is missing: $RelativePath"
        }
    }

    foreach ($RelativePath in @(
        "alembic/versions",
        "static/assets",
        "data/common_words",
        "data/demo",
        "data/worldpacks",
        "app/core/indexing/data"
    )) {
        $RequiredDirectory = Join-Path $InternalDirectory $RelativePath
        if (-not (Test-Path -LiteralPath $RequiredDirectory -PathType Container)) {
            throw "Packaged runtime resource directory is missing: $RelativePath"
        }
        if (-not (Get-ChildItem -LiteralPath $RequiredDirectory -File -Recurse | Select-Object -First 1)) {
            throw "Packaged runtime resource directory is empty: $RelativePath"
        }
    }

    & $RuntimeExecutable --help
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged runtime help smoke failed."
    }

    Write-Output $RuntimeDirectory
} finally {
    Pop-Location
    [Environment]::SetEnvironmentVariable("PYTHONUTF8", $PreviousPythonUtf8, "Process")
    [Environment]::SetEnvironmentVariable(
        "UV_PROJECT_ENVIRONMENT",
        $PreviousUvProjectEnvironment,
        "Process"
    )
    [Environment]::SetEnvironmentVariable("VITE_API_URL", $PreviousViteApiUrl, "Process")
    [Environment]::SetEnvironmentVariable(
        "VITE_DEPLOY_MODE",
        $PreviousViteDeployMode,
        "Process"
    )
}
