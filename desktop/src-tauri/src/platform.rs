use std::io;

use thiserror::Error;
use windows_sys::Win32::System::SystemInformation::{IMAGE_FILE_MACHINE, IMAGE_FILE_MACHINE_AMD64};
use windows_sys::Win32::System::Threading::{GetCurrentProcess, IsWow64Process2};
use windows_version::OsVersion;

// Windows 10 2004 — the oldest build covered by the WebView2 Evergreen runtime
// and the bundled Python runtime.
const MINIMUM_WINDOWS_BUILD: u32 = 19_041;

#[derive(Debug, Error)]
pub enum UnsupportedWindowsPlatform {
    #[error(
        "NovWr requires Windows 10 build {MINIMUM_WINDOWS_BUILD} or newer; found Windows build {build}"
    )]
    UnsupportedBuild { build: u32 },
    #[error("inspect native Windows machine architecture: {source}")]
    ArchitectureInspection {
        #[source]
        source: io::Error,
    },
    #[error("NovWr requires native x64 Windows; found native machine type 0x{native_machine:04X}")]
    UnsupportedArchitecture { native_machine: IMAGE_FILE_MACHINE },
}

pub fn require_supported_windows_x64() -> Result<(), UnsupportedWindowsPlatform> {
    require_supported_build(OsVersion::current().build)?;
    let native_machine = current_native_machine()
        .map_err(|source| UnsupportedWindowsPlatform::ArchitectureInspection { source })?;
    require_native_x64(native_machine)
}

fn require_supported_build(build: u32) -> Result<(), UnsupportedWindowsPlatform> {
    if build < MINIMUM_WINDOWS_BUILD {
        return Err(UnsupportedWindowsPlatform::UnsupportedBuild { build });
    }
    Ok(())
}

fn current_native_machine() -> io::Result<IMAGE_FILE_MACHINE> {
    let mut process_machine = 0;
    let mut native_machine = 0;
    let succeeded = unsafe {
        IsWow64Process2(
            GetCurrentProcess(),
            &mut process_machine,
            &mut native_machine,
        )
    };
    if succeeded == 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(native_machine)
}

fn require_native_x64(
    native_machine: IMAGE_FILE_MACHINE,
) -> Result<(), UnsupportedWindowsPlatform> {
    if native_machine != IMAGE_FILE_MACHINE_AMD64 {
        return Err(UnsupportedWindowsPlatform::UnsupportedArchitecture { native_machine });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use windows_sys::Win32::System::SystemInformation::IMAGE_FILE_MACHINE_ARM64;

    #[test]
    fn rejects_pre_2004_builds_and_accepts_windows_10_and_11() {
        assert!(require_supported_build(17_763).is_err());
        assert!(require_supported_build(19_040).is_err());
        assert!(require_supported_build(19_041).is_ok());
        assert!(require_supported_build(19_045).is_ok());
        assert!(require_supported_build(22_000).is_ok());
        assert!(require_supported_build(26_100).is_ok());
    }

    #[test]
    fn accepts_only_native_x64_windows() {
        assert!(require_native_x64(IMAGE_FILE_MACHINE_AMD64).is_ok());
        assert!(require_native_x64(IMAGE_FILE_MACHINE_ARM64).is_err());
    }
}
