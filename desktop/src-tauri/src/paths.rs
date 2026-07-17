use std::fs;
use std::io;
use std::path::{Path, PathBuf};

const PRODUCT_DIRECTORY_NAME: &str = "NovWr";
const DATA_DIRECTORY_NAME: &str = "data";
const LOGS_DIRECTORY_NAME: &str = "logs";
const APP_DIRECTORY_NAME: &str = "app";
const SECRET_FILE_NAME: &str = "runtime-secret.json";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AppPaths {
    pub root: PathBuf,
    pub data: PathBuf,
    pub logs: PathBuf,
    pub app: PathBuf,
    pub secret: PathBuf,
}

impl AppPaths {
    pub fn from_local_data_root(local_data_root: impl AsRef<Path>) -> Self {
        let root = local_data_root.as_ref().join(PRODUCT_DIRECTORY_NAME);
        Self {
            data: root.join(DATA_DIRECTORY_NAME),
            logs: root.join(LOGS_DIRECTORY_NAME),
            app: root.join(APP_DIRECTORY_NAME),
            secret: root.join(SECRET_FILE_NAME),
            root,
        }
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
}
