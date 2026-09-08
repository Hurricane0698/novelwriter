use std::ffi::OsStr;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

const PRODUCT_DIRECTORY_NAME: &str = "NovWr";
const DATA_DIRECTORY_NAME: &str = "data";
const LOGS_DIRECTORY_NAME: &str = "logs";
const APP_DIRECTORY_NAME: &str = "app";
const SECRET_FILE_NAME: &str = "runtime-secret.json";
const LLM_CONFIG_FILE_NAME: &str = "llm-config.json";
pub const DATA_ROOT_OVERRIDE_ENV: &str = "NOVWR_DESKTOP_DATA_ROOT";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AppPaths {
    pub root: PathBuf,
    pub data: PathBuf,
    pub logs: PathBuf,
    pub app: PathBuf,
    pub secret: PathBuf,
    pub llm_config: PathBuf,
}

impl AppPaths {
    pub fn from_local_data_root(local_data_root: impl AsRef<Path>) -> Self {
        let root = local_data_root.as_ref().join(PRODUCT_DIRECTORY_NAME);
        Self::from_owned_root(root)
    }

    fn from_owned_root(root: PathBuf) -> Self {
        Self {
            data: root.join(DATA_DIRECTORY_NAME),
            logs: root.join(LOGS_DIRECTORY_NAME),
            app: root.join(APP_DIRECTORY_NAME),
            secret: root.join(SECRET_FILE_NAME),
            llm_config: root.join(LLM_CONFIG_FILE_NAME),
            root,
        }
    }

    #[cfg(target_os = "macos")]
    pub fn from_macos_roots(application_support: impl AsRef<Path>, logs: impl AsRef<Path>) -> Self {
        let mut paths = Self::from_local_data_root(application_support);
        paths.logs = logs.as_ref().join(PRODUCT_DIRECTORY_NAME);
        paths
    }

    pub fn with_root_override(&self, value: Option<&OsStr>) -> io::Result<Self> {
        let Some(value) = value else {
            return Ok(self.clone());
        };
        let root = PathBuf::from(value);
        if !root.is_absolute() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                format!("{DATA_ROOT_OVERRIDE_ENV} must be an absolute directory"),
            ));
        }
        Ok(Self::from_owned_root(root))
    }

    pub fn create_directories(&self) -> io::Result<()> {
        for directory in [&self.root, &self.data, &self.logs] {
            fs::create_dir_all(directory)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};

    static NEXT_TEST_DIRECTORY_ID: AtomicU64 = AtomicU64::new(0);

    struct TestDirectory(PathBuf);

    impl TestDirectory {
        fn new(label: &str) -> Self {
            let timestamp = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock must be after the Unix epoch")
                .as_nanos();
            let sequence = NEXT_TEST_DIRECTORY_ID.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!(
                "novwr-paths-{label}-{}-{timestamp}-{sequence}",
                std::process::id()
            ));
            fs::create_dir(&path).expect("test directory must be created");
            Self(path)
        }

        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn local_data_root_maps_to_the_exact_novwr_tree() {
        let local_data_root = TestDirectory::new("mapping");

        let paths = AppPaths::from_local_data_root(local_data_root.path());

        let expected_root = local_data_root.path().join("NovWr");
        assert_eq!(paths.root, expected_root);
        assert_eq!(paths.data, expected_root.join("data"));
        assert_eq!(paths.logs, expected_root.join("logs"));
        assert_eq!(paths.app, expected_root.join("app"));
        assert_eq!(paths.secret, expected_root.join("runtime-secret.json"));
        assert_eq!(paths.llm_config, expected_root.join("llm-config.json"));
        assert_eq!(paths.llm_config.parent(), Some(paths.root.as_path()));
        assert_ne!(paths.llm_config.parent(), Some(paths.data.as_path()));
    }

    #[test]
    fn directory_creation_creates_owned_directories_without_creating_secret() {
        let local_data_root = TestDirectory::new("create");
        let paths = AppPaths::from_local_data_root(local_data_root.path());

        paths
            .create_directories()
            .expect("NovWr directories must be created");

        for directory in [&paths.root, &paths.data, &paths.logs] {
            assert!(
                directory.is_dir(),
                "{} must be a directory",
                directory.display()
            );
        }
        assert!(!paths.app.exists());
        assert!(!paths.secret.exists());
        assert!(!paths.llm_config.exists());
    }

    #[test]
    fn directory_creation_stops_at_the_first_invalid_path() {
        let local_data_root = TestDirectory::new("fail-fast");
        let paths = AppPaths::from_local_data_root(local_data_root.path());
        fs::create_dir_all(&paths.root).expect("NovWr root must be created");
        fs::write(&paths.data, b"not a directory").expect("conflicting data path must be created");

        let error = paths
            .create_directories()
            .expect_err("a file at the data directory path must fail");

        assert_ne!(error.kind(), io::ErrorKind::NotFound);
        assert!(paths.data.is_file());
        assert!(!paths.logs.exists());
        assert!(!paths.app.exists());
    }

    #[test]
    fn explicit_root_override_is_exact_and_keeps_every_file_inside_the_profile() {
        let defaults = AppPaths::from_local_data_root("unused-default");
        let directory = TestDirectory::new("override");
        let root = directory.path().join("隔离 profile");
        let paths = defaults.with_root_override(Some(root.as_os_str())).unwrap();
        assert_eq!(paths.root, root);
        assert_eq!(paths.data, root.join("data"));
        assert_eq!(paths.logs, root.join("logs"));
        assert_eq!(paths.secret, root.join("runtime-secret.json"));
        assert_eq!(paths.llm_config, root.join("llm-config.json"));
        assert_eq!(defaults.with_root_override(None).unwrap(), defaults);
        assert!(
            !root.exists(),
            "resolving paths must not touch the filesystem"
        );
    }

    #[test]
    fn root_override_rejects_relative_and_empty_values() {
        let defaults = AppPaths::from_local_data_root("unused-default");
        for value in [
            "",
            "relative/profile",
            "~/Library/Application Support/NovWr",
        ] {
            let error = defaults
                .with_root_override(Some(OsStr::new(value)))
                .unwrap_err();
            assert_eq!(error.kind(), io::ErrorKind::InvalidInput);
        }
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn macos_defaults_keep_application_support_and_logs_in_native_locations() {
        let paths = AppPaths::from_macos_roots(
            "/Users/test/Library/Application Support",
            "/Users/test/Library/Logs",
        );
        assert_eq!(
            paths.root,
            PathBuf::from("/Users/test/Library/Application Support/NovWr")
        );
        assert_eq!(paths.logs, PathBuf::from("/Users/test/Library/Logs/NovWr"));
        assert_eq!(paths.data, paths.root.join("data"));
    }
}
