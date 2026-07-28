#Requires -Version 7.2

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$SetupPath,

    [ValidateRange(1, 900)]
    [int]$InstallerTimeoutSeconds = 300,

    [ValidateRange(1, 300)]
    [int]$HealthTimeoutSeconds = 180,

    [ValidateRange(1, 120)]
    [int]$CleanupTimeoutSeconds = 30,

    [ValidateRange(1, 600)]
    [int]$PlaywrightTimeoutSeconds = 480
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$HealthUrl = "http://127.0.0.1:8000/api/health"
$SpaUrl = "http://127.0.0.1:8000/"
$Port = 8000
$ProcessTopologyTimeoutSeconds = 15
$WindowStateTimeoutSeconds = 15
$LlmProviderTimeoutSeconds = 15
$LlmConfigApiKey = "novwr-desktop-installed-secret"
$LlmConfigModel = "novwr-desktop-installed-model"
$ForbiddenLlmLogValues = @(
    $LlmConfigApiKey,
    "Reply with exactly: ok",
    'Return a JSON object: {"ok": true}'
)
$env:OPENAI_LOG = "debug"
$script:TrackedProcessHandles = @()

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class NovWrNativeWindow
{
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool IsWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool IsWindowVisible(IntPtr hWnd);
}
"@

function Wait-ForCondition {
    param(
        [Parameter(Mandatory)] [scriptblock] $Condition,
        [Parameter(Mandatory)] [int] $TimeoutSeconds,
        [Parameter(Mandatory)] [string] $FailureMessage
    )

    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (& $Condition) {
            return
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $Deadline)

    throw $FailureMessage
}

function Start-LlmProviderStub {
    param(
        [Parameter(Mandatory)] [string] $RootDirectory,
        [Parameter(Mandatory)] [string] $RunnerTemp,
        [Parameter(Mandatory)] [string] $ApiKey,
        [Parameter(Mandatory)] [string] $Model,
        [Parameter(Mandatory)] [int] $TimeoutSeconds
    )

    $ScriptPath = Join-Path $RootDirectory "scripts/desktop_llm_provider_stub.mjs"
    if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
        throw "The desktop LLM provider stub is missing: $ScriptPath"
    }
    $ReadyPath = Join-Path $RunnerTemp "novwr-desktop-llm-provider-ready.json"
    $LogPath = Join-Path $RunnerTemp "novwr-desktop-llm-provider.log"
    Remove-Item -LiteralPath $ReadyPath, $LogPath -Force -ErrorAction SilentlyContinue

    $NodeCommand = Get-Command node.exe -ErrorAction Stop
    $StartInfo = [Diagnostics.ProcessStartInfo]::new()
    $StartInfo.FileName = $NodeCommand.Source
    $StartInfo.WorkingDirectory = $RootDirectory
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true
    [void]$StartInfo.ArgumentList.Add($ScriptPath)
    [void]$StartInfo.ArgumentList.Add("--ready-file")
    [void]$StartInfo.ArgumentList.Add($ReadyPath)
    [void]$StartInfo.ArgumentList.Add("--log-file")
    [void]$StartInfo.ArgumentList.Add($LogPath)
    $StartInfo.Environment["NOVWR_DESKTOP_PROVIDER_API_KEY"] = $ApiKey
    $StartInfo.Environment["NOVWR_DESKTOP_PROVIDER_MODEL"] = $Model

    $Process = [Diagnostics.Process]::new()
    $Process.StartInfo = $StartInfo
    if (-not $Process.Start()) {
        $Process.Dispose()
        throw "The desktop LLM provider stub did not start."
    }

    try {
        Wait-ForCondition -TimeoutSeconds $TimeoutSeconds -FailureMessage "The desktop LLM provider stub did not become ready within $TimeoutSeconds seconds." -Condition {
            if ($Process.HasExited) {
                throw "The desktop LLM provider stub exited with code $($Process.ExitCode) before becoming ready."
            }
            return Test-Path -LiteralPath $ReadyPath -PathType Leaf
        }
        $Ready = Get-Content -LiteralPath $ReadyPath -Raw | ConvertFrom-Json
        $BaseUrl = [string]$Ready.base_url
        $BaseUri = $null
        if (
            -not [Uri]::TryCreate($BaseUrl, [UriKind]::Absolute, [ref]$BaseUri) -or
            $BaseUri.Scheme -cne "http" -or
            $BaseUri.Host -cne "127.0.0.1" -or
            $BaseUri.AbsolutePath -cne "/v1"
        ) {
            throw "The desktop LLM provider stub returned an invalid base URL: $BaseUrl"
        }
        $Health = Invoke-RestMethod -Uri "$($Ready.origin)/health" -TimeoutSec 5
        if ($Health.status -cne "healthy") {
            throw "The desktop LLM provider stub did not report healthy status."
        }
        return [pscustomobject]@{
            Process = $Process
            BaseUrl = $BaseUrl
            Origin = [string]$Ready.origin
            LogPath = $LogPath
        }
    } catch {
        try {
            if (-not $Process.HasExited) {
                $Process.Kill()
                [void]$Process.WaitForExit(5000)
            }
        } finally {
            $Process.Dispose()
        }
        throw
    }
}

function Assert-LlmProviderProbeCount {
    param(
        [Parameter(Mandatory)] [string] $Origin,
        [Parameter(Mandatory)] [int] $ExpectedCount
    )

    $Health = Invoke-RestMethod -Uri "$Origin/health" -TimeoutSec 5
    foreach ($Mode in @("basic", "stream", "json_mode")) {
        $ActualCount = [int]$Health.requests.$Mode
        if ($ActualCount -ne $ExpectedCount) {
            throw "Expected $ExpectedCount successful $Mode provider probes; received $ActualCount."
        }
    }
}

function Write-LlmProviderDiagnostics {
    param([Parameter(Mandatory)] [AllowEmptyString()] [string] $LogPath)

    Write-Output "Desktop LLM provider stub diagnostics:"
    if ([string]::IsNullOrWhiteSpace($LogPath)) {
        Write-Output "(provider log path was not initialized)"
        return
    }
    if (Test-Path -LiteralPath $LogPath -PathType Leaf) {
        Get-Content -LiteralPath $LogPath -Raw -ErrorAction SilentlyContinue | Write-Output
    } else {
        Write-Output "(provider log file was not created)"
    }
}

function Stop-LlmProviderStub {
    param(
        [Parameter(Mandatory)] [object] $Process,
        [Parameter(Mandatory)] [int] $TimeoutSeconds
    )

    try {
        if (-not $Process.HasExited) {
            $Process.Kill()
            if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
                throw "The desktop LLM provider stub did not exit within $TimeoutSeconds seconds."
            }
        }
    } finally {
        $Process.Dispose()
    }
}

function Assert-FileDoesNotContainUtf8Text {
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [string[]] $Values
    )

    $Bytes = [IO.File]::ReadAllBytes($Path)
    if ($Bytes.Length -eq 0) {
        throw "Expected an encrypted non-empty file: $Path"
    }
    $Decoded = [Text.Encoding]::UTF8.GetString($Bytes)
    foreach ($Value in $Values) {
        if ($Decoded.Contains($Value, [StringComparison]::Ordinal)) {
            throw "Encrypted file contains forbidden plaintext '$Value': $Path"
        }
    }
}

function Assert-DirectoryFilesDoNotContainUtf8Text {
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [string[]] $Values
    )

    foreach ($File in Get-ChildItem -LiteralPath $Path -File -Recurse) {
        $Decoded = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($File.FullName))
        foreach ($Value in $Values) {
            if ($Decoded.Contains($Value, [StringComparison]::Ordinal)) {
                throw "Log file contains forbidden plaintext '$Value': $($File.FullName)"
            }
        }
    }
}

function Wait-ForVisibleMainWindowHandle {
    param(
        [Parameter(Mandatory)] [object] $DesktopProcessHandle,
        [Parameter(Mandatory)] [int] $TimeoutSeconds
    )

    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ($DesktopProcessHandle.HasExited) {
            throw "The NovWr desktop process exited before its main window became visible."
        }
        $DesktopProcessHandle.Refresh()
        $WindowHandle = $DesktopProcessHandle.MainWindowHandle
        if (
            $WindowHandle -ne [IntPtr]::Zero -and
            [NovWrNativeWindow]::IsWindowVisible($WindowHandle)
        ) {
            return $WindowHandle
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $Deadline)

    throw "The NovWr main window did not become visible within $TimeoutSeconds seconds."
}

function Wait-ForWindowVisibility {
    param(
        [Parameter(Mandatory)] [IntPtr] $WindowHandle,
        [Parameter(Mandatory)] [bool] $ExpectedVisible,
        [Parameter(Mandatory)] [int] $TimeoutSeconds
    )

    $ExpectedState = if ($ExpectedVisible) { "visible" } else { "hidden" }
    Wait-ForCondition -TimeoutSeconds $TimeoutSeconds -FailureMessage "The NovWr main window did not become $ExpectedState within $TimeoutSeconds seconds." -Condition {
        return [NovWrNativeWindow]::IsWindowVisible($WindowHandle) -eq $ExpectedVisible
    }
}

function Invoke-ProcessWithDeadline {
    param(
        [Parameter(Mandatory)] [string] $FilePath,
        [Parameter(Mandatory)] [string[]] $ArgumentList,
        [Parameter(Mandatory)] [int] $TimeoutSeconds,
        [Parameter(Mandatory)] [string] $Label
    )

    $Process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -PassThru
    if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
        try {
            & taskkill.exe /PID $Process.Id /T /F | Out-Null
            if (-not $Process.WaitForExit(5000)) {
                Stop-Process -Id $Process.Id -Force -ErrorAction Stop
            }
        } catch {
            Write-Warning "Unable to terminate timed-out ${Label}: $($_.Exception.Message)"
        }
        throw "$Label exceeded its $TimeoutSeconds second deadline."
    }

    $Process.Refresh()
    if ($Process.ExitCode -ne 0) {
        throw "$Label failed with exit code $($Process.ExitCode)."
    }
}

function Write-PlaywrightDiagnostics {
    param(
        [Parameter(Mandatory)] [string] $StdoutPath,
        [Parameter(Mandatory)] [string] $StderrPath
    )

    foreach ($LogPath in @($StdoutPath, $StderrPath)) {
        Write-Output "Playwright output from ${LogPath}:"
        if (Test-Path -LiteralPath $LogPath -PathType Leaf) {
            Get-Content -LiteralPath $LogPath -Raw -ErrorAction SilentlyContinue | Write-Output
        } else {
            Write-Output "(log file was not created)"
        }
    }
}

function Write-PlaywrightSuccessOutput {
    param(
        [Parameter(Mandatory)] [string] $Phase,
        [Parameter(Mandatory)] [string] $StdoutPath
    )

    Write-Output "Installed-product Playwright ${Phase} stdout:"
    if (Test-Path -LiteralPath $StdoutPath -PathType Leaf) {
        Get-Content -LiteralPath $StdoutPath -Raw -ErrorAction SilentlyContinue | Write-Output
    } else {
        Write-Output "(stdout log file was not created)"
    }
}

function Invoke-InstalledProductPlaywright {
    param(
        [Parameter(Mandatory)] [string] $Phase,
        [Parameter(Mandatory)] [string] $SpecPath,
        [Parameter(Mandatory)] [string] $WebRoot,
        [Parameter(Mandatory)] [string] $StatePath,
        [Parameter(Mandatory)] [string] $LlmBaseUrl,
        [Parameter(Mandatory)] [string] $LlmApiKey,
        [Parameter(Mandatory)] [string] $LlmModel,
        [Parameter(Mandatory)] [int] $TimeoutSeconds
    )

    $StdoutPath = Join-Path $env:RUNNER_TEMP "novwr-playwright-${Phase}.stdout.log"
    $StderrPath = Join-Path $env:RUNNER_TEMP "novwr-playwright-${Phase}.stderr.log"
    Remove-Item -LiteralPath $StdoutPath, $StderrPath -Force -ErrorAction SilentlyContinue

    $PlaywrightEnvironment = [ordered]@{
        NOVWR_DESKTOP_E2E_STATE = $StatePath
        NOVWR_DESKTOP_E2E_LLM_BASE_URL = $LlmBaseUrl
        NOVWR_DESKTOP_E2E_LLM_API_KEY = $LlmApiKey
        NOVWR_DESKTOP_E2E_LLM_MODEL = $LlmModel
    }
    $PreviousEnvironment = @{}
    try {
        foreach ($Entry in $PlaywrightEnvironment.GetEnumerator()) {
            $PreviousEnvironment[$Entry.Key] = [Environment]::GetEnvironmentVariable(
                $Entry.Key,
                [EnvironmentVariableTarget]::Process
            )
            [Environment]::SetEnvironmentVariable(
                $Entry.Key,
                $Entry.Value,
                [EnvironmentVariableTarget]::Process
            )
        }
        $Process = Start-Process `
            -FilePath "npm.cmd" `
            -ArgumentList @("run", "test:e2e:desktop-installed", "--", $SpecPath) `
            -WorkingDirectory $WebRoot `
            -RedirectStandardOutput $StdoutPath `
            -RedirectStandardError $StderrPath `
            -PassThru
    } finally {
        foreach ($Entry in $PlaywrightEnvironment.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable(
                $Entry.Key,
                $PreviousEnvironment[$Entry.Key],
                [EnvironmentVariableTarget]::Process
            )
        }
    }

    if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
        try {
            & taskkill.exe /PID $Process.Id /T /F | Out-Null
            if (-not $Process.WaitForExit(5000)) {
                Stop-Process -Id $Process.Id -Force -ErrorAction Stop
            }
        } catch {
            Write-Warning "Unable to terminate timed-out installed-product Playwright ${Phase}: $($_.Exception.Message)"
        }
        Write-PlaywrightDiagnostics -StdoutPath $StdoutPath -StderrPath $StderrPath
        throw "Installed-product Playwright ${Phase} exceeded its $TimeoutSeconds second deadline."
    }

    $Process.WaitForExit()
    $Process.Refresh()
    if ($Process.ExitCode -ne 0) {
        Write-PlaywrightDiagnostics -StdoutPath $StdoutPath -StderrPath $StderrPath
        throw "Installed-product Playwright ${Phase} failed with exit code $($Process.ExitCode)."
    }
    Write-PlaywrightSuccessOutput -Phase $Phase -StdoutPath $StdoutPath
}

function Test-PortBindable {
    $Listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    try {
        $Listener.Start()
        return $true
    } catch [Net.Sockets.SocketException] {
        return $false
    } finally {
        $Listener.Stop()
    }
}

function ConvertFrom-ExtendedWindowsPath {
    param([Parameter(Mandatory)] [AllowEmptyString()] [string] $Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }
    if ($Path.StartsWith('\\?\UNC\', [StringComparison]::OrdinalIgnoreCase)) {
        return '\\' + $Path.Substring(8)
    }
    if ($Path.StartsWith('\\?\', [StringComparison]::OrdinalIgnoreCase)) {
        return $Path.Substring(4)
    }
    return $Path
}

function Test-ExecutablePathEquals {
    param(
        [Parameter(Mandatory)] [AllowEmptyString()] [string] $ActualPath,
        [Parameter(Mandatory)] [string] $ExpectedPath
    )

    $NormalizedActualPath = ConvertFrom-ExtendedWindowsPath -Path $ActualPath
    $NormalizedExpectedPath = ConvertFrom-ExtendedWindowsPath -Path $ExpectedPath
    return (
        -not [string]::IsNullOrWhiteSpace($NormalizedActualPath) -and
        $NormalizedActualPath.Equals($NormalizedExpectedPath, [StringComparison]::OrdinalIgnoreCase)
    )
}

function Get-RuntimeCommand {
    param(
        [Parameter(Mandatory)] [object] $Process,
        [Parameter(Mandatory)] [string] $RuntimeExecutable
    )

    if ([string]::IsNullOrWhiteSpace($Process.CommandLine)) {
        return $null
    }
    $CommandLineMatch = [regex]::Match(
        $Process.CommandLine,
        '^(?:"(?<executable>[^"]+)"|(?<executable>\S+)) (?<command>serve|worker)$',
        [Text.RegularExpressions.RegexOptions]::CultureInvariant
    )
    if (-not $CommandLineMatch.Success) {
        return $null
    }
    if (-not (Test-ExecutablePathEquals -ActualPath $CommandLineMatch.Groups["executable"].Value -ExpectedPath $RuntimeExecutable)) {
        return $null
    }
    return $CommandLineMatch.Groups["command"].Value
}

function Test-CimProcessIdentityEquals {
    param(
        [Parameter(Mandatory)] [object] $ExpectedProcess,
        [Parameter(Mandatory)] [object] $ActualProcess
    )

    if (
        $null -eq $ExpectedProcess.CreationDate -or
        $null -eq $ActualProcess.CreationDate -or
        [string]::IsNullOrWhiteSpace([string]$ExpectedProcess.CommandLine) -or
        [string]::IsNullOrWhiteSpace([string]$ActualProcess.CommandLine)
    ) {
        return $false
    }
    return (
        [uint32]$ActualProcess.ProcessId -eq [uint32]$ExpectedProcess.ProcessId -and
        [DateTime]$ActualProcess.CreationDate -eq [DateTime]$ExpectedProcess.CreationDate -and
        [string]$ActualProcess.Name -ceq [string]$ExpectedProcess.Name -and
        (Test-ExecutablePathEquals -ActualPath ([string]$ActualProcess.ExecutablePath) -ExpectedPath ([string]$ExpectedProcess.ExecutablePath)) -and
        [uint32]$ActualProcess.ParentProcessId -eq [uint32]$ExpectedProcess.ParentProcessId -and
        [string]$ActualProcess.CommandLine -ceq [string]$ExpectedProcess.CommandLine
    )
}

function Close-ProcessHandles {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [object[]] $ProcessHandles
    )

    $FirstFailure = $null
    foreach ($ProcessHandle in $ProcessHandles) {
        if ($null -eq $ProcessHandle) {
            continue
        }
        try {
            $ProcessHandle.Dispose()
        } catch {
            if ($null -eq $FirstFailure) {
                $FirstFailure = $_.Exception
            }
        }
    }
    if ($null -ne $FirstFailure) {
        throw $FirstFailure
    }
}

function Open-ValidatedProcessHandle {
    param([Parameter(Mandatory)] [object] $ExpectedProcess)

    $ProcessId = [int]$ExpectedProcess.ProcessId
    $ProcessHandle = $null
    try {
        $ProcessHandle = [Diagnostics.Process]::GetProcessById($ProcessId)
        [void]$ProcessHandle.Handle
        $RequeriedProcesses = @(
            Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId"
        )
        if (
            $RequeriedProcesses.Count -ne 1 -or
            -not (Test-CimProcessIdentityEquals -ExpectedProcess $ExpectedProcess -ActualProcess $RequeriedProcesses[0]) -or
            $ProcessHandle.HasExited
        ) {
            throw "Process $ProcessId changed identity while its handle was being pinned."
        }
        return $ProcessHandle
    } catch {
        $ValidationFailure = $_.Exception
        if ($null -ne $ProcessHandle) {
            try {
                Close-ProcessHandles -ProcessHandles @($ProcessHandle)
            } catch {
                Write-Warning "Unable to close rejected process handle ${ProcessId}: $($_.Exception.Message)"
            }
        }
        throw $ValidationFailure
    }
}

function Wait-ForProcessHandlesExit {
    param(
        [Parameter(Mandatory)] [AllowEmptyCollection()] [object[]] $ProcessHandles,
        [Parameter(Mandatory)] [int] $TimeoutSeconds
    )

    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    foreach ($ProcessHandle in $ProcessHandles) {
        if ($ProcessHandle.HasExited) {
            continue
        }
        $RemainingMilliseconds = [int][Math]::Floor(
            [Math]::Max(0, ($Deadline - [DateTime]::UtcNow).TotalMilliseconds)
        )
        if ($RemainingMilliseconds -le 0 -or -not $ProcessHandle.WaitForExit($RemainingMilliseconds)) {
            return $false
        }
    }
    return $true
}

function Stop-ValidatedProcessHandles {
    param(
        [Parameter(Mandatory)] [AllowEmptyCollection()] [object[]] $ProcessHandles,
        [Parameter(Mandatory)] [int] $TimeoutSeconds
    )

    $FirstFailure = $null
    foreach ($ProcessHandle in $ProcessHandles) {
        try {
            if (-not $ProcessHandle.HasExited) {
                $ProcessHandle.Kill()
            }
        } catch {
            $KillFailure = $_.Exception
            try {
                if ($ProcessHandle.HasExited) {
                    continue
                }
            } catch {
                $KillFailure = $_.Exception
            }
            if ($null -eq $FirstFailure) {
                $FirstFailure = $KillFailure
            }
        }
    }
    if (-not (Wait-ForProcessHandlesExit -ProcessHandles $ProcessHandles -TimeoutSeconds $TimeoutSeconds)) {
        throw "Validated NovWr process handles did not exit within $TimeoutSeconds seconds."
    }
    if ($null -ne $FirstFailure) {
        throw $FirstFailure
    }
}

function Get-InstalledProcesses {
    param(
        [Parameter(Mandatory)] [string] $InstallRoot,
        [object[]] $ProcessSnapshot = @()
    )

    if (-not $PSBoundParameters.ContainsKey("ProcessSnapshot")) {
        $ProcessSnapshot = @(Get-CimInstance Win32_Process)
    }
    $NormalizedInstallRoot = ConvertFrom-ExtendedWindowsPath -Path $InstallRoot
    $InstallPrefix = $NormalizedInstallRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    return @(
        $ProcessSnapshot | Where-Object {
            $ExecutablePath = ConvertFrom-ExtendedWindowsPath -Path ([string]$_.ExecutablePath)
            -not [string]::IsNullOrWhiteSpace($ExecutablePath) -and
            $ExecutablePath.StartsWith($InstallPrefix, [StringComparison]::OrdinalIgnoreCase)
        }
    )
}

function Stop-InstalledProcessesSafely {
    param(
        [Parameter(Mandatory)] [string] $InstallRoot,
        [Parameter(Mandatory)] [int] $TimeoutSeconds
    )

    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $ProcessSnapshot = @(Get-CimInstance Win32_Process)
        $InstalledProcesses = @(
            Get-InstalledProcesses -InstallRoot $InstallRoot -ProcessSnapshot $ProcessSnapshot
        )
        if ($InstalledProcesses.Count -eq 0) {
            return
        }

        $ValidatedHandles = @()
        try {
            foreach ($InstalledProcess in $InstalledProcesses) {
                try {
                    $ValidatedHandles += Open-ValidatedProcessHandle -ExpectedProcess $InstalledProcess
                } catch {
                    Write-Warning "Unable to pin installed NovWr process $($InstalledProcess.ProcessId) for final cleanup: $($_.Exception.Message)"
                }
            }
            if ($ValidatedHandles.Count -gt 0) {
                $RemainingSeconds = [int][Math]::Ceiling(
                    [Math]::Max(1, ($Deadline - [DateTime]::UtcNow).TotalSeconds)
                )
                Stop-ValidatedProcessHandles -ProcessHandles $ValidatedHandles -TimeoutSeconds $RemainingSeconds
            }
        } catch {
            Write-Warning "Validated final NovWr cleanup failed: $($_.Exception.Message)"
        } finally {
            try {
                Close-ProcessHandles -ProcessHandles $ValidatedHandles
            } catch {
                Write-Warning "Unable to close final cleanup process handles: $($_.Exception.Message)"
            }
        }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $Deadline)

    $RemainingProcesses = @(Get-InstalledProcesses -InstallRoot $InstallRoot)
    if ($RemainingProcesses.Count -gt 0) {
        Write-Warning "Final cleanup left $($RemainingProcesses.Count) identity-unverified NovWr processes running."
    }
}

function Assert-ProcessTopology {
    param(
        [Parameter(Mandatory)] [string] $InstallRoot,
        [Parameter(Mandatory)] [string] $DesktopExecutable
    )

    $ProcessSnapshot = @(Get-CimInstance Win32_Process)
    $Processes = @(
        Get-InstalledProcesses -InstallRoot $InstallRoot -ProcessSnapshot $ProcessSnapshot
    )
    $DesktopName = [IO.Path]::GetFileName($DesktopExecutable)
    $RuntimeExecutable = Join-Path (Join-Path $InstallRoot "runtime") "novwr-runtime.exe"
    $DesktopProcesses = @(
        $Processes | Where-Object {
            $_.Name -ieq $DesktopName -and
            (Test-ExecutablePathEquals -ActualPath ([string]$_.ExecutablePath) -ExpectedPath $DesktopExecutable)
        }
    )
    $OwnedRuntimeProcesses = @(
        $Processes | Where-Object {
            $_.Name -ieq "novwr-runtime.exe" -and
            (Test-ExecutablePathEquals -ActualPath ([string]$_.ExecutablePath) -ExpectedPath $RuntimeExecutable)
        }
    )
    $RuntimeProcesses = @(
        if ($DesktopProcesses.Count -eq 1) {
            $DesktopProcessId = [uint32]$DesktopProcesses[0].ProcessId
            $OwnedRuntimeProcesses | Where-Object {
                [uint32]$_.ParentProcessId -eq $DesktopProcessId
            }
        }
    )
    $RuntimeRoles = @(
        foreach ($RuntimeProcess in $RuntimeProcesses) {
            [pscustomobject]@{
                Process = $RuntimeProcess
                Command = Get-RuntimeCommand -Process $RuntimeProcess -RuntimeExecutable $RuntimeExecutable
            }
        }
    )
    $ServeProcesses = @(
        $RuntimeRoles | Where-Object { $_.Command -ceq "serve" }
    )
    $WorkerProcesses = @(
        $RuntimeRoles | Where-Object { $_.Command -ceq "worker" }
    )

    if (
        $Processes.Count -ne 3 -or
        $DesktopProcesses.Count -ne 1 -or
        $OwnedRuntimeProcesses.Count -ne 2 -or
        $RuntimeProcesses.Count -ne 2 -or
        $ServeProcesses.Count -ne 1 -or
        $WorkerProcesses.Count -ne 1
    ) {
        $DesktopProcessIds = @($DesktopProcesses | ForEach-Object { [uint32]$_.ProcessId })
        $RenderedProcesses = $ProcessSnapshot |
            Where-Object {
                $_.Name -ieq $DesktopName -or
                $_.Name -ieq "novwr-runtime.exe" -or
                $DesktopProcessIds -contains [uint32]$_.ParentProcessId
            } |
            Select-Object ProcessId, ParentProcessId, CreationDate, Name, ExecutablePath, CommandLine |
            Format-List |
            Out-String
        throw "Unexpected installed process topology:`n$RenderedProcesses"
    }

    $ProcessHandles = @()
    try {
        $DesktopHandle = Open-ValidatedProcessHandle -ExpectedProcess $DesktopProcesses[0]
        $ProcessHandles += $DesktopHandle
        $RuntimeHandles = @(
            foreach ($RuntimeProcess in $RuntimeProcesses) {
                $RuntimeHandle = Open-ValidatedProcessHandle -ExpectedProcess $RuntimeProcess
                $ProcessHandles += $RuntimeHandle
                $RuntimeHandle
            }
        )
        return [pscustomobject]@{
            Desktop = $DesktopProcesses[0]
            Runtimes = $RuntimeProcesses
            All = $Processes
            DesktopHandle = $DesktopHandle
            RuntimeHandles = $RuntimeHandles
            ProcessHandles = $ProcessHandles
        }
    } catch {
        $TopologyFailure = $_.Exception
        try {
            Close-ProcessHandles -ProcessHandles $ProcessHandles
        } catch {
            Write-Warning "Unable to close rejected topology process handles: $($_.Exception.Message)"
        }
        throw $TopologyFailure
    }
}

function Wait-ForProcessTopology {
    param(
        [Parameter(Mandatory)] [string] $InstallRoot,
        [Parameter(Mandatory)] [string] $DesktopExecutable
    )

    $Deadline = [DateTime]::UtcNow.AddSeconds($ProcessTopologyTimeoutSeconds)
    $LastError = "processes were not inspected"
    do {
        try {
            return Assert-ProcessTopology -InstallRoot $InstallRoot -DesktopExecutable $DesktopExecutable
        } catch {
            $LastError = $_.Exception.Message
            Start-Sleep -Milliseconds 500
        }
    } while ([DateTime]::UtcNow -lt $Deadline)

    throw "The installed process topology did not stabilize within $ProcessTopologyTimeoutSeconds seconds. Last observation: $LastError"
}

function Wait-ForHealthyDesktopCandidates {
    param(
        [Parameter(Mandatory)] [object[]] $Candidates,
        [Parameter(Mandatory)] [int] $TimeoutSeconds
    )

    Wait-ForCondition -TimeoutSeconds $TimeoutSeconds -FailureMessage "NovWr did not become healthy at $HealthUrl." -Condition {
        $RunningCandidates = @(
            foreach ($Candidate in $Candidates) {
                if (Get-Process -Id $Candidate.Id -ErrorAction SilentlyContinue) {
                    $Candidate
                }
            }
        )
        if ($RunningCandidates.Count -eq 0) {
            throw "All concurrent NovWr desktop candidates exited before the backend became healthy."
        }
        try {
            $Health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
            return $Health.status -eq "healthy"
        } catch {
            return $false
        }
    }
}

function Assert-HealthyApplication {
    try {
        $Health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 5
    } catch {
        throw "The NovWr backend was not reachable after the main window closed: $($_.Exception.Message)"
    }
    if ($Health.status -ne "healthy") {
        throw "The NovWr backend was not healthy after the main window closed."
    }
}

function Assert-SpaRoot {
    $Response = Invoke-WebRequest -Uri $SpaUrl -UseBasicParsing -TimeoutSec 5
    if ($Response.StatusCode -ne 200 -or $Response.Content -notmatch '<div id="root">') {
        throw "The installed runtime did not serve the NovWr SPA root."
    }
}

function Start-AndVerifyDesktop {
    param(
        [Parameter(Mandatory)] [string] $DesktopExecutable,
        [Parameter(Mandatory)] [string] $InstallRoot
    )

    $StartupContenders = @(
        (Start-Process -FilePath $DesktopExecutable -PassThru)
        (Start-Process -FilePath $DesktopExecutable -PassThru)
    )
    Wait-ForHealthyDesktopCandidates -Candidates $StartupContenders -TimeoutSeconds $HealthTimeoutSeconds
    Assert-SpaRoot
    $Topology = Wait-ForProcessTopology -InstallRoot $InstallRoot -DesktopExecutable $DesktopExecutable
    $PrimaryDesktopProcessId = [int]$Topology.Desktop.ProcessId
    $script:TrackedProcessHandles = @($Topology.ProcessHandles)

    foreach ($Contender in $StartupContenders) {
        if ($Contender.Id -eq $PrimaryDesktopProcessId) {
            continue
        }
        if (-not $Contender.WaitForExit(15000)) {
            Stop-Process -Id $Contender.Id -Force -ErrorAction SilentlyContinue
            throw "A concurrent cold-start NovWr contender remained running instead of yielding to the primary instance."
        }
        $Contender.Refresh()
        if ($Contender.ExitCode -ne 0) {
            throw "A concurrent cold-start NovWr contender exited with code $($Contender.ExitCode) instead of yielding cleanly."
        }
    }

    return $Topology
}

function Stop-DesktopAndAssertCleanup {
    param(
        [Parameter(Mandatory)] [object] $Topology,
        [Parameter(Mandatory)] [string] $InstallRoot
    )

    $DesktopHandle = $Topology.DesktopHandle
    $RuntimeHandles = @($Topology.RuntimeHandles)
    $ProcessHandles = @($Topology.ProcessHandles)
    if ($null -eq $DesktopHandle -or $RuntimeHandles.Count -ne 2 -or $ProcessHandles.Count -ne 3) {
        throw "Cleanup requires one pinned desktop handle and two pinned runtime handles."
    }
    $CleanupCompleted = $false
    try {
        try {
            if (-not $DesktopHandle.HasExited) {
                $DesktopHandle.Kill()
            }
        } catch {
            if (-not $DesktopHandle.HasExited) {
                throw
            }
        }
        if (-not (Wait-ForProcessHandlesExit -ProcessHandles $ProcessHandles -TimeoutSeconds $CleanupTimeoutSeconds)) {
            throw "The desktop Job Object left installed child processes running."
        }
        Wait-ForCondition -TimeoutSeconds $CleanupTimeoutSeconds -FailureMessage "The desktop Job Object left installed child processes running." -Condition {
            return @(Get-InstalledProcesses -InstallRoot $InstallRoot).Count -eq 0
        }
        Wait-ForCondition -TimeoutSeconds $CleanupTimeoutSeconds -FailureMessage "Port 8000 was not released after the desktop process exited." -Condition {
            return Test-PortBindable
        }
        $CleanupCompleted = $true
    } finally {
        if ($CleanupCompleted) {
            try {
                Close-ProcessHandles -ProcessHandles $ProcessHandles
            } finally {
                $script:TrackedProcessHandles = @()
            }
        }
    }
}

function Write-FailureDiagnostics {
    param(
        [Parameter(Mandatory)] [string] $InstallRoot,
        [Parameter(Mandatory)] [string] $LogRoot
    )

    $ProcessSnapshot = @(Get-CimInstance Win32_Process)
    $InstalledProcesses = @(
        Get-InstalledProcesses -InstallRoot $InstallRoot -ProcessSnapshot $ProcessSnapshot
    )
    $InstalledProcessIds = @($InstalledProcesses | ForEach-Object { [uint32]$_.ProcessId })
    $DesktopProcessIds = @(
        $InstalledProcesses |
            Where-Object { $_.Name -ieq "NovWr.exe" } |
            ForEach-Object { [uint32]$_.ProcessId }
    )

    Write-Output "NovWr process diagnostics:"
    $ProcessSnapshot |
        Where-Object {
            $InstalledProcessIds -contains [uint32]$_.ProcessId -or
            $DesktopProcessIds -contains [uint32]$_.ParentProcessId -or
            $_.Name -ieq "NovWr.exe" -or
            $_.Name -ieq "novwr-runtime.exe"
        } |
        Select-Object ProcessId, ParentProcessId, CreationDate, Name, ExecutablePath, CommandLine |
        Format-List |
        Out-String |
        Write-Output

    if (Test-Path -LiteralPath $LogRoot -PathType Container) {
        foreach ($LogFile in Get-ChildItem -LiteralPath $LogRoot -File -Recurse) {
            Write-Output "Last 120 lines of $($LogFile.FullName):"
            Get-Content -LiteralPath $LogFile.FullName -Tail 120 -ErrorAction SilentlyContinue
        }
    }
}

if ($env:OS -ne "Windows_NT") {
    throw "The desktop installer smoke test requires Windows."
}
if ($env:CI -ne "true" -or $env:NOVWR_INSTALLER_SMOKE_ALLOW_DATA_RESET -ne "1") {
    throw "Set CI=true and NOVWR_INSTALLER_SMOKE_ALLOW_DATA_RESET=1 to authorize destructive cleanup of the ephemeral NovWr CI profile."
}

$WindowsVersion = [Environment]::OSVersion.Version
if ($WindowsVersion.Major -ne 10 -or $WindowsVersion.Build -lt 22000) {
    throw "The NovWr desktop preview supports Windows 11 only; found $WindowsVersion."
}
$ProcessArchitecture = [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
if ($ProcessArchitecture -ne "X64") {
    throw "The NovWr desktop preview supports x64 only; found $ProcessArchitecture."
}

$RootDirectory = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$WebRoot = Join-Path $RootDirectory "web"
if ([string]::IsNullOrWhiteSpace($env:RUNNER_TEMP)) {
    throw "RUNNER_TEMP is required for installed-product Playwright state and diagnostics."
}
if (-not [IO.Path]::IsPathRooted($SetupPath)) {
    $SetupPath = Join-Path $RootDirectory $SetupPath
}
$SetupPath = [IO.Path]::GetFullPath($SetupPath)
if (-not (Test-Path -LiteralPath $SetupPath -PathType Leaf)) {
    throw "The NSIS setup executable is missing: $SetupPath"
}

$ProductRoot = Join-Path $env:LOCALAPPDATA "NovWr"
$InstallRoot = Join-Path $ProductRoot "app"
$DataRoot = Join-Path $ProductRoot "data"
$LogRoot = Join-Path $ProductRoot "logs"
$DatabasePath = Join-Path $DataRoot "novels.db"
$SecretPath = Join-Path $ProductRoot "runtime-secret.json"
$LlmConfigPath = Join-Path $ProductRoot "llm-config.json"
$SentinelPath = Join-Path $DataRoot "installer-smoke-sentinel.txt"
$LogSentinelPath = Join-Path $LogRoot "installer-smoke-log-sentinel.txt"
$UninstallRegistryPath = "Registry::HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Uninstall\NovWr"
$ManufacturerProductRegistryPath = $null
$PlaywrightStatePath = Join-Path $env:RUNNER_TEMP "novwr-desktop-installed-state.json"
$LlmProvider = $null
$LlmProviderLogPath = ""
$LlmConfigBaseUrl = ""

if (-not (Test-PortBindable)) {
    throw "Port 8000 is already occupied before the installer smoke test."
}
if (@(Get-InstalledProcesses -InstallRoot $InstallRoot).Count -ne 0) {
    throw "Installed NovWr processes are already running before the installer smoke test."
}
if (Test-Path -LiteralPath $UninstallRegistryPath) {
    throw "NovWr installer metadata already exists before the installer smoke test: $UninstallRegistryPath"
}

if (Test-Path -LiteralPath $ProductRoot) {
    Remove-Item -LiteralPath $ProductRoot -Recurse -Force
}
Remove-Item -LiteralPath $PlaywrightStatePath -Force -ErrorAction SilentlyContinue

try {
    $LlmProvider = Start-LlmProviderStub `
        -RootDirectory $RootDirectory `
        -RunnerTemp $env:RUNNER_TEMP `
        -ApiKey $LlmConfigApiKey `
        -Model $LlmConfigModel `
        -TimeoutSeconds $LlmProviderTimeoutSeconds
    $LlmProviderLogPath = $LlmProvider.LogPath
    $LlmConfigBaseUrl = $LlmProvider.BaseUrl

    Invoke-ProcessWithDeadline -FilePath $SetupPath -ArgumentList @("/S", "/NS") -TimeoutSeconds $InstallerTimeoutSeconds -Label "Silent NovWr install"

    if (-not (Test-Path -LiteralPath $InstallRoot -PathType Container)) {
        throw "NovWr was not installed at the required current-user path: $InstallRoot"
    }
    if (-not (Test-Path -LiteralPath $UninstallRegistryPath)) {
        throw "The NovWr current-user uninstall registry entry is missing: $UninstallRegistryPath"
    }
    $Publisher = [string](
        Get-ItemPropertyValue -LiteralPath $UninstallRegistryPath -Name "Publisher"
    )
    if ([string]::IsNullOrWhiteSpace($Publisher)) {
        throw "The NovWr uninstall registry entry does not declare its publisher."
    }
    $ManufacturerProductRegistryPath = "Registry::HKEY_CURRENT_USER\Software\$Publisher\NovWr"
    if (-not (Test-Path -LiteralPath $ManufacturerProductRegistryPath)) {
        throw "The NovWr installer product registry entry is missing: $ManufacturerProductRegistryPath"
    }
    $TopLevelExecutables = @(
        Get-ChildItem -LiteralPath $InstallRoot -Filter "*.exe" -File |
            Where-Object { $_.Name -ine "uninstall.exe" }
    )
    if ($TopLevelExecutables.Count -ne 1) {
        throw "The installed app root must contain exactly one desktop executable; found $($TopLevelExecutables.Count)."
    }
    $DesktopExecutable = $TopLevelExecutables[0].FullName

    $InitialTopology = Start-AndVerifyDesktop -DesktopExecutable $DesktopExecutable -InstallRoot $InstallRoot
    $InitialProcessIds = (($InitialTopology.All.ProcessId | Sort-Object) -join ",")
    Invoke-InstalledProductPlaywright -Phase "initial" -SpecPath "e2e/desktop-installed/initial.spec.ts" `
        -WebRoot $WebRoot `
        -StatePath $PlaywrightStatePath `
        -LlmBaseUrl $LlmConfigBaseUrl `
        -LlmApiKey $LlmConfigApiKey `
        -LlmModel $LlmConfigModel `
        -TimeoutSeconds $PlaywrightTimeoutSeconds
    Assert-LlmProviderProbeCount -Origin $LlmProvider.Origin -ExpectedCount 1
    if (-not (Test-Path -LiteralPath $PlaywrightStatePath -PathType Leaf)) {
        throw "Initial installed-product Playwright did not persist its shared state file: $PlaywrightStatePath"
    }

    $DesktopProcess = $InitialTopology.DesktopHandle
    $MainWindowHandle = Wait-ForVisibleMainWindowHandle -DesktopProcessHandle $DesktopProcess -TimeoutSeconds $WindowStateTimeoutSeconds
    $DesktopProcess.Refresh()
    if ($DesktopProcess.MainWindowHandle -ne $MainWindowHandle) {
        throw "The NovWr main window handle changed before WM_CLOSE was sent."
    }
    if (-not $DesktopProcess.CloseMainWindow()) {
        throw "CloseMainWindow could not send WM_CLOSE to the NovWr main window."
    }
    Wait-ForWindowVisibility -WindowHandle $MainWindowHandle -ExpectedVisible $false -TimeoutSeconds $WindowStateTimeoutSeconds
    if (-not [NovWrNativeWindow]::IsWindow($MainWindowHandle)) {
        throw "WM_CLOSE destroyed the NovWr main window instead of hiding it to the tray."
    }
    $HiddenTopology = Wait-ForProcessTopology -InstallRoot $InstallRoot -DesktopExecutable $DesktopExecutable
    try {
        $HiddenProcessIds = (($HiddenTopology.All.ProcessId | Sort-Object) -join ",")
        if ($HiddenProcessIds -ne $InitialProcessIds) {
            throw "Closing the main window changed the stable NovWr process group."
        }
    } finally {
        Close-ProcessHandles -ProcessHandles @($HiddenTopology.ProcessHandles)
    }
    Assert-HealthyApplication

    $Duplicate = Start-Process -FilePath $DesktopExecutable -PassThru
    if (-not $Duplicate.WaitForExit(15000)) {
        Stop-Process -Id $Duplicate.Id -Force -ErrorAction SilentlyContinue
        throw "A duplicate NovWr launch remained running instead of reopening the existing window."
    }
    $Duplicate.Refresh()
    if ($Duplicate.ExitCode -ne 0) {
        throw "A duplicate NovWr launch exited with code $($Duplicate.ExitCode) instead of signaling the existing window cleanly."
    }
    Wait-ForWindowVisibility -WindowHandle $MainWindowHandle -ExpectedVisible $true -TimeoutSeconds $WindowStateTimeoutSeconds
    $ReopenedDesktopProcess = $InitialTopology.DesktopHandle
    $ReopenedDesktopProcess.Refresh()
    if ($ReopenedDesktopProcess.MainWindowHandle -ne $MainWindowHandle) {
        throw "The duplicate launch did not reopen the same NovWr main window handle."
    }
    $StableTopology = Wait-ForProcessTopology -InstallRoot $InstallRoot -DesktopExecutable $DesktopExecutable
    try {
        $StableProcessIds = (($StableTopology.All.ProcessId | Sort-Object) -join ",")
        if ($StableProcessIds -ne $InitialProcessIds) {
            throw "A duplicate launch replaced or added to the stable NovWr process group."
        }
    } finally {
        Close-ProcessHandles -ProcessHandles @($StableTopology.ProcessHandles)
    }

    Stop-DesktopAndAssertCleanup -Topology $InitialTopology -InstallRoot $InstallRoot

    foreach ($RequiredPath in @($DatabasePath, $SecretPath)) {
        if (-not (Test-Path -LiteralPath $RequiredPath -PathType Leaf)) {
            throw "The installed application did not persist required state: $RequiredPath"
        }
    }
    if (-not (Test-Path -LiteralPath $LlmConfigPath -PathType Leaf)) {
        throw "The installed application did not persist its encrypted LLM configuration: $LlmConfigPath"
    }
    Assert-FileDoesNotContainUtf8Text `
        -Path $LlmConfigPath `
        -Values @($LlmConfigBaseUrl, $LlmConfigApiKey, $LlmConfigModel)
    if (-not (Test-Path -LiteralPath $LogRoot -PathType Container)) {
        throw "The installed application did not create its persistent log directory: $LogRoot"
    }
    Assert-DirectoryFilesDoNotContainUtf8Text -Path $LogRoot -Values $ForbiddenLlmLogValues

    $SentinelValue = "novwr-installer-smoke-$([Guid]::NewGuid())"
    $LogSentinelValue = "novwr-installer-log-smoke-$([Guid]::NewGuid())"
    Set-Content -LiteralPath $SentinelPath -Value $SentinelValue -NoNewline
    Set-Content -LiteralPath $LogSentinelPath -Value $LogSentinelValue -NoNewline
    $InstallRootBeforeReinstallCreationTimeUtc = [datetime]"2001-01-01T00:00:00Z"
    [IO.Directory]::SetCreationTimeUtc($InstallRoot, $InstallRootBeforeReinstallCreationTimeUtc)
    $InstallRootBeforeReinstallCreationTimeUtc = [IO.Directory]::GetCreationTimeUtc($InstallRoot)
    $SecretBeforeReinstall = [Convert]::ToBase64String([IO.File]::ReadAllBytes($SecretPath))
    $LlmConfigBeforeReinstall = [Convert]::ToBase64String([IO.File]::ReadAllBytes($LlmConfigPath))

    Invoke-ProcessWithDeadline -FilePath $SetupPath -ArgumentList @("/P", "/NS") -TimeoutSeconds $InstallerTimeoutSeconds -Label "Passive NovWr overwrite install"

    if (-not (Test-Path -LiteralPath $DatabasePath -PathType Leaf)) {
        throw "Overwrite installation removed novels.db."
    }
    if ([IO.Directory]::GetCreationTimeUtc($InstallRoot) -eq $InstallRootBeforeReinstallCreationTimeUtc) {
        throw "Overwrite installation did not recreate the previous app directory."
    }
    if ((Get-Content -LiteralPath $SentinelPath -Raw) -ne $SentinelValue) {
        throw "Overwrite installation changed persistent user data."
    }
    if ((Get-Content -LiteralPath $LogSentinelPath -Raw) -ne $LogSentinelValue) {
        throw "Overwrite installation changed persistent logs."
    }
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($SecretPath)) -ne $SecretBeforeReinstall) {
        throw "Overwrite installation replaced the persistent runtime secret."
    }
    if (-not (Test-Path -LiteralPath $LlmConfigPath -PathType Leaf)) {
        throw "Overwrite installation removed the encrypted LLM configuration."
    }
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($LlmConfigPath)) -ne $LlmConfigBeforeReinstall) {
        throw "Overwrite installation changed the encrypted LLM configuration."
    }

    $RestartedTopology = Start-AndVerifyDesktop -DesktopExecutable $DesktopExecutable -InstallRoot $InstallRoot
    Invoke-InstalledProductPlaywright -Phase "restart" -SpecPath "e2e/desktop-installed/restart.spec.ts" `
        -WebRoot $WebRoot `
        -StatePath $PlaywrightStatePath `
        -LlmBaseUrl $LlmConfigBaseUrl `
        -LlmApiKey $LlmConfigApiKey `
        -LlmModel $LlmConfigModel `
        -TimeoutSeconds $PlaywrightTimeoutSeconds
    Assert-LlmProviderProbeCount -Origin $LlmProvider.Origin -ExpectedCount 2
    Stop-DesktopAndAssertCleanup -Topology $RestartedTopology -InstallRoot $InstallRoot
    Assert-DirectoryFilesDoNotContainUtf8Text -Path $LogRoot -Values $ForbiddenLlmLogValues

    $Uninstaller = Join-Path $InstallRoot "uninstall.exe"
    if (-not (Test-Path -LiteralPath $Uninstaller -PathType Leaf)) {
        throw "The NSIS uninstaller is missing: $Uninstaller"
    }
    Invoke-ProcessWithDeadline -FilePath $Uninstaller -ArgumentList @("/S") -TimeoutSeconds $InstallerTimeoutSeconds -Label "Silent NovWr uninstall"

    # NSIS hands off to a temporary uninstaller copy before the installed launcher exits.
    Wait-ForCondition -TimeoutSeconds $InstallerTimeoutSeconds -FailureMessage "Silent uninstall did not reach the installer-owned terminal state." -Condition {
        return (
            -not (Test-Path -LiteralPath $InstallRoot) -and
            -not (Test-Path -LiteralPath $LlmConfigPath) -and
            -not (Test-Path -LiteralPath $UninstallRegistryPath) -and
            -not (Test-Path -LiteralPath $ManufacturerProductRegistryPath)
        )
    }

    if (Test-Path -LiteralPath $InstallRoot) {
        throw "Silent uninstall did not remove the NovWr app directory."
    }
    if (Test-Path -LiteralPath $LlmConfigPath) {
        throw "Silent uninstall did not remove the encrypted LLM configuration."
    }
    foreach ($RequiredPersistentPath in @($DataRoot, $LogRoot, $DatabasePath, $SecretPath, $SentinelPath, $LogSentinelPath)) {
        if (-not (Test-Path -LiteralPath $RequiredPersistentPath)) {
            throw "Silent uninstall removed persistent NovWr state: $RequiredPersistentPath"
        }
    }
    if ((Get-Content -LiteralPath $SentinelPath -Raw) -ne $SentinelValue) {
        throw "Silent uninstall changed the persistent data sentinel."
    }
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($SecretPath)) -ne $SecretBeforeReinstall) {
        throw "Silent uninstall changed the persistent runtime secret."
    }
    if ((Get-Content -LiteralPath $LogSentinelPath -Raw) -ne $LogSentinelValue) {
        throw "Silent uninstall changed persistent logs."
    }
    foreach ($RemovedRegistryPath in @($UninstallRegistryPath, $ManufacturerProductRegistryPath)) {
        if (Test-Path -LiteralPath $RemovedRegistryPath) {
            throw "Silent uninstall left installer-owned registry metadata: $RemovedRegistryPath"
        }
    }

    Write-Output "Windows desktop installer smoke test passed."
} catch {
    Write-FailureDiagnostics -InstallRoot $InstallRoot -LogRoot $LogRoot
    Write-LlmProviderDiagnostics -LogPath $LlmProviderLogPath
    throw
} finally {
    if ($null -ne $LlmProvider) {
        try {
            Stop-LlmProviderStub -Process $LlmProvider.Process -TimeoutSeconds $CleanupTimeoutSeconds
        } catch {
            Write-Warning "Desktop LLM provider stub cleanup failed: $($_.Exception.Message)"
        }
    }
    $TrackedProcessHandles = @($script:TrackedProcessHandles)
    try {
        if ($TrackedProcessHandles.Count -gt 0) {
            Stop-ValidatedProcessHandles -ProcessHandles $TrackedProcessHandles -TimeoutSeconds $CleanupTimeoutSeconds
        }
    } catch {
        Write-Warning "Tracked NovWr process cleanup failed: $($_.Exception.Message)"
    } finally {
        try {
            Close-ProcessHandles -ProcessHandles $TrackedProcessHandles
        } catch {
            Write-Warning "Unable to close tracked NovWr process handles: $($_.Exception.Message)"
        } finally {
            $script:TrackedProcessHandles = @()
        }
    }
    Stop-InstalledProcessesSafely -InstallRoot $InstallRoot -TimeoutSeconds $CleanupTimeoutSeconds
}
