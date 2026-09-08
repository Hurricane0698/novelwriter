#[cfg(target_os = "macos")]
pub(crate) use crate::macos::{
    DEFAULT_TERMINATION_EXIT_CODE, EnvironmentDelta, JobObject, ManagedProcess, ProcessCommand,
    ShutdownEvent, single_instance,
};
#[cfg(target_os = "windows")]
pub(crate) use crate::windows::{
    DEFAULT_TERMINATION_EXIT_CODE, EnvironmentDelta, JobObject, ManagedProcess, ProcessCommand,
    ShutdownEvent, open_directory, single_instance,
};

#[cfg(target_os = "macos")]
pub use macos_support::{UnsupportedPlatform, open_directory, require_supported};
#[cfg(target_os = "windows")]
pub use windows_support::{
    UnsupportedWindowsPlatform as UnsupportedPlatform,
    require_supported_windows_x64 as require_supported,
};

#[cfg(target_os = "windows")]
mod windows_support {
    use std::io;

    use thiserror::Error;
    use windows_sys::Win32::System::SystemInformation::{
        IMAGE_FILE_MACHINE, IMAGE_FILE_MACHINE_AMD64,
    };
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
        #[error(
            "NovWr requires native x64 Windows; found native machine type 0x{native_machine:04X}"
        )]
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

    impl UnsupportedWindowsPlatform {
        pub fn user_summary(&self) -> &'static str {
            "NovWr 需要 Windows 10（2004 及以上）或 Windows 11 的 x64 版本。"
        }
    }
}

#[cfg(target_os = "macos")]
mod macos_support {
    use std::io;
    use std::path::Path;
    use std::process::{Command, Stdio};

    const MINIMUM_MACOS_MAJOR: u32 = 14;

    #[derive(Debug, thiserror::Error)]
    pub enum UnsupportedPlatform {
        #[error("inspect macOS version: {0}")]
        VersionInspection(#[source] io::Error),
        #[error("NovWr requires macOS {MINIMUM_MACOS_MAJOR} or newer; found {version}")]
        UnsupportedVersion { version: String },
        #[error("NovWr requires Apple Silicon; found {architecture}")]
        UnsupportedArchitecture { architecture: &'static str },
    }

    impl UnsupportedPlatform {
        pub fn user_summary(&self) -> &'static str {
            "NovWr 需要运行 macOS 14 或更新版本的 Apple Silicon Mac。"
        }
    }

    pub fn require_supported() -> Result<(), UnsupportedPlatform> {
        require_architecture(std::env::consts::ARCH)?;
        let output = Command::new("/usr/bin/sw_vers")
            .arg("-productVersion")
            .stdin(Stdio::null())
            .output()
            .map_err(UnsupportedPlatform::VersionInspection)?;
        if !output.status.success() {
            return Err(UnsupportedPlatform::VersionInspection(io::Error::other(
                "sw_vers failed to report the operating system version",
            )));
        }
        let version = String::from_utf8(output.stdout).map_err(|error| {
            UnsupportedPlatform::VersionInspection(io::Error::new(
                io::ErrorKind::InvalidData,
                error,
            ))
        })?;
        require_version(version.trim())
    }

    fn require_architecture(architecture: &'static str) -> Result<(), UnsupportedPlatform> {
        if architecture != "aarch64" {
            return Err(UnsupportedPlatform::UnsupportedArchitecture { architecture });
        }
        Ok(())
    }

    fn require_version(version: &str) -> Result<(), UnsupportedPlatform> {
        let major = version
            .split('.')
            .next()
            .and_then(|part| part.parse::<u32>().ok());
        if !matches!(major, Some(major) if major >= MINIMUM_MACOS_MAJOR) {
            return Err(UnsupportedPlatform::UnsupportedVersion {
                version: version.to_owned(),
            });
        }
        Ok(())
    }

    fn directory_open_command(path: &Path) -> io::Result<Command> {
        if !path.is_absolute() || !path.is_dir() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                format!("directory must exist and be absolute: {}", path.display()),
            ));
        }
        let mut command = Command::new("/usr/bin/open");
        // The absolute path is a single argument; shell syntax is never interpreted.
        command.arg(path).stdin(Stdio::null());
        Ok(command)
    }

    pub fn open_directory(path: &Path) -> io::Result<()> {
        let status = directory_open_command(path)?.status()?;
        if !status.success() {
            return Err(io::Error::other(format!(
                "open directory failed with status {status}"
            )));
        }
        Ok(())
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use std::ffi::OsStr;

        #[test]
        fn requires_apple_silicon_and_macos_fourteen_or_later() {
            assert!(require_architecture("aarch64").is_ok());
            assert!(require_architecture("x86_64").is_err());
            for version in ["", "invalid", "10.15.7", "11.7", "12.7", "13.6"] {
                assert!(require_version(version).is_err());
            }
            for version in ["14.0", "14.6.1", "26.0"] {
                assert!(require_version(version).is_ok());
            }
        }

        #[test]
        fn finder_receives_one_literal_absolute_path_argument() {
            let root = tempfile::tempdir().unwrap();
            let path = root.path().join("小说 data; shell $literal");
            std::fs::create_dir(&path).unwrap();
            let command = directory_open_command(&path).unwrap();
            assert_eq!(command.get_program(), OsStr::new("/usr/bin/open"));
            assert_eq!(
                command.get_args().collect::<Vec<_>>(),
                vec![path.as_os_str()]
            );
            assert!(directory_open_command(Path::new("relative")).is_err());
            assert!(directory_open_command(&root.path().join("missing")).is_err());
        }
    }
}
