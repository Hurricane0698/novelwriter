use serde::{Deserialize, Serialize};
use std::error::Error;
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

#[cfg(target_os = "windows")]
use std::os::windows::ffi::OsStrExt;
#[cfg(target_os = "windows")]
use windows_sys::Win32::Storage::FileSystem::{MOVEFILE_WRITE_THROUGH, MoveFileExW};

pub const SECRET_SCHEMA_VERSION: u32 = 1;
pub const MINIMUM_SECRET_BYTES: usize = 32;
const TEMP_FILE_RANDOM_BYTES: usize = 16;
const MAXIMUM_TEMP_FILE_ATTEMPTS: usize = 16;

#[derive(Debug)]
pub enum SecretError {
    Io {
        operation: &'static str,
        path: PathBuf,
        source: io::Error,
    },
    Json {
        path: PathBuf,
        source: serde_json::Error,
    },
    Random {
        source: getrandom::Error,
    },
    UnsupportedVersion {
        found: u32,
    },
    InvalidEncoding {
        source: hex::FromHexError,
    },
    TooShort {
        actual_bytes: usize,
        minimum_bytes: usize,
    },
}

impl fmt::Display for SecretError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io {
                operation,
                path,
                source,
            } => write!(
                formatter,
                "failed to {operation} desktop secret at {}: {source}",
                path.display()
            ),
            Self::Json { path, source } => write!(
                formatter,
                "desktop secret at {} is not valid versioned JSON: {source}",
                path.display()
            ),
            Self::Random { source } => {
                write!(
                    formatter,
                    "failed to obtain operating-system randomness: {source}"
                )
            }
            Self::UnsupportedVersion { found } => write!(
                formatter,
                "desktop secret schema version {found} is unsupported"
            ),
            Self::InvalidEncoding { source } => {
                write!(formatter, "desktop secret encoding is invalid: {source}")
            }
            Self::TooShort {
                actual_bytes,
                minimum_bytes,
            } => write!(
                formatter,
                "desktop secret contains {actual_bytes} bytes; at least {minimum_bytes} are required"
            ),
        }
    }
}

impl Error for SecretError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Io { source, .. } => Some(source),
            Self::Json { source, .. } => Some(source),
            Self::InvalidEncoding { source } => Some(source),
            Self::Random { .. } | Self::UnsupportedVersion { .. } | Self::TooShort { .. } => None,
        }
    }
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct SecretDocument {
    version: u32,
    secret: String,
}

pub fn load_or_create_secret(path: impl AsRef<Path>) -> Result<String, SecretError> {
    let path = path.as_ref();
    match load_secret(path) {
        Ok(secret) => Ok(secret),
        Err(SecretError::Io { source, .. }) if source.kind() == io::ErrorKind::NotFound => {
            create_secret(path)
        }
        Err(error) => Err(error),
    }
}

fn load_secret(path: &Path) -> Result<String, SecretError> {
    let bytes = fs::read(path).map_err(|source| io_error("read", path, source))?;
    let document: SecretDocument =
        serde_json::from_slice(&bytes).map_err(|source| SecretError::Json {
            path: path.to_path_buf(),
            source,
        })?;
    validate_document(document)
}

fn create_secret(path: &Path) -> Result<String, SecretError> {
    let mut random_bytes = [0_u8; MINIMUM_SECRET_BYTES];
    getrandom::fill(&mut random_bytes).map_err(|source| SecretError::Random { source })?;
    let document = SecretDocument {
        version: SECRET_SCHEMA_VERSION,
        secret: hex::encode(random_bytes),
    };
    let mut serialized = serde_json::to_vec(&document).map_err(|source| SecretError::Json {
        path: path.to_path_buf(),
        source,
    })?;
    serialized.push(b'\n');

    let (temporary_path, mut file) = create_temporary_file(path)?;

    file.write_all(&serialized)
        .map_err(|source| io_error("write", &temporary_path, source))?;
    file.sync_all()
        .map_err(|source| io_error("sync", &temporary_path, source))?;
    drop(file);

    match persist_temporary_file(&temporary_path, path) {
        Ok(()) => Ok(document.secret),
        Err(persist_source) => {
            let _ = fs::remove_file(&temporary_path);
            match load_secret(path) {
                Ok(secret) => Ok(secret),
                Err(SecretError::Io { source, .. }) if source.kind() == io::ErrorKind::NotFound => {
                    Err(io_error("persist", path, persist_source))
                }
                Err(error) => Err(error),
            }
        }
    }
}

fn create_temporary_file(path: &Path) -> Result<(PathBuf, File), SecretError> {
    let parent = path.parent().ok_or_else(|| {
        io_error(
            "resolve parent directory for",
            path,
            io::Error::new(
                io::ErrorKind::InvalidInput,
                "desktop secret path has no parent directory",
            ),
        )
    })?;

    for _ in 0..MAXIMUM_TEMP_FILE_ATTEMPTS {
        let mut suffix_bytes = [0_u8; TEMP_FILE_RANDOM_BYTES];
        getrandom::fill(&mut suffix_bytes).map_err(|source| SecretError::Random { source })?;
        let temporary_path = parent.join(format!(
            ".novwr-runtime-secret-{}.tmp",
            hex::encode(suffix_bytes)
        ));
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary_path)
        {
            Ok(file) => return Ok((temporary_path, file)),
            Err(source) if source.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(source) => return Err(io_error("create", &temporary_path, source)),
        }
    }

    Err(io_error(
        "create unique temporary file for",
        path,
        io::Error::new(
            io::ErrorKind::AlreadyExists,
            "exhausted unique desktop secret temporary file attempts",
        ),
    ))
}

#[cfg(target_os = "windows")]
fn persist_temporary_file(temporary_path: &Path, path: &Path) -> io::Result<()> {
    let temporary_path = encode_windows_path(temporary_path)?;
    let path = encode_windows_path(path)?;
    let moved = unsafe {
        MoveFileExW(
            temporary_path.as_ptr(),
            path.as_ptr(),
            MOVEFILE_WRITE_THROUGH,
        )
    };
    if moved == 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

#[cfg(target_os = "windows")]
fn encode_windows_path(path: &Path) -> io::Result<Vec<u16>> {
    let mut encoded: Vec<u16> = path.as_os_str().encode_wide().collect();
    if encoded.contains(&0) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "desktop secret path contains an embedded NUL",
        ));
    }
    encoded.push(0);
    Ok(encoded)
}

#[cfg(not(target_os = "windows"))]
fn persist_temporary_file(temporary_path: &Path, path: &Path) -> io::Result<()> {
    // Unit tests run on non-Windows hosts. A same-directory hard link preserves the
    // Windows no-replace commit semantics before removing the temporary name.
    fs::hard_link(temporary_path, path)?;
    fs::remove_file(temporary_path)
}

fn validate_document(document: SecretDocument) -> Result<String, SecretError> {
    if document.version != SECRET_SCHEMA_VERSION {
        return Err(SecretError::UnsupportedVersion {
            found: document.version,
        });
    }

    let decoded =
        hex::decode(&document.secret).map_err(|source| SecretError::InvalidEncoding { source })?;
    if decoded.len() < MINIMUM_SECRET_BYTES {
        return Err(SecretError::TooShort {
            actual_bytes: decoded.len(),
            minimum_bytes: MINIMUM_SECRET_BYTES,
        });
    }
    Ok(document.secret)
}

fn io_error(operation: &'static str, path: &Path, source: io::Error) -> SecretError {
    SecretError::Io {
        operation,
        path: path.to_path_buf(),
        source,
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
                "novwr-secret-{label}-{}-{timestamp}-{sequence}",
                std::process::id()
            ));
            fs::create_dir(&path).expect("test directory must be created");
            Self(path)
        }

        fn secret_path(&self) -> PathBuf {
            self.0.join("runtime-secret.json")
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn creates_a_versioned_secret_from_os_randomness() {
        let directory = TestDirectory::new("create");
        let path = directory.secret_path();

        let secret = load_or_create_secret(&path).expect("secret must be created");

        let stored: SecretDocument =
            serde_json::from_slice(&fs::read(&path).expect("secret file must be readable"))
                .expect("secret file must contain valid JSON");
        assert_eq!(stored.version, SECRET_SCHEMA_VERSION);
        assert_eq!(stored.secret, secret);
        assert_eq!(hex::decode(secret).expect("secret must be hex").len(), 32);
        assert_eq!(
            fs::read_dir(&directory.0)
                .expect("secret directory must be readable")
                .count(),
            1
        );
    }

    #[test]
    fn reuses_an_existing_secret_without_rewriting_the_file() {
        let directory = TestDirectory::new("reuse");
        let path = directory.secret_path();
        let expected_secret = "ab".repeat(MINIMUM_SECRET_BYTES);
        fs::write(
            &path,
            format!("{{\"version\":{SECRET_SCHEMA_VERSION},\"secret\":\"{expected_secret}\"}}\n"),
        )
        .expect("existing secret must be written");
        let original_bytes = fs::read(&path).expect("existing secret must be readable");

        let loaded = load_or_create_secret(&path).expect("existing secret must load");

        assert_eq!(loaded, expected_secret);
        assert_eq!(
            fs::read(&path).expect("existing secret must remain readable"),
            original_bytes
        );
    }

    #[test]
    fn concurrent_creation_loads_the_winner_without_overwriting_it() {
        let directory = TestDirectory::new("concurrent");
        let path = directory.secret_path();
        let winning_secret = "cd".repeat(MINIMUM_SECRET_BYTES);
        let winning_document =
            format!("{{\"version\":{SECRET_SCHEMA_VERSION},\"secret\":\"{winning_secret}\"}}\n");
        fs::write(&path, winning_document.as_bytes()).expect("winning secret must be written");

        let loaded = create_secret(&path).expect("concurrent winner must be loaded");

        assert_eq!(loaded, winning_secret);
        assert_eq!(
            fs::read(&path).expect("winning secret must remain readable"),
            winning_document.as_bytes()
        );
        assert_eq!(
            fs::read_dir(&directory.0)
                .expect("secret directory must be readable")
                .count(),
            1
        );
    }

    #[test]
    fn invalid_json_fails_without_replacing_the_file() {
        let directory = TestDirectory::new("invalid-json");
        let path = directory.secret_path();
        let original_bytes = b"not-json".to_vec();
        fs::write(&path, &original_bytes).expect("invalid secret must be written");

        let error = load_or_create_secret(&path).expect_err("invalid JSON must fail");

        assert!(matches!(error, SecretError::Json { .. }));
        assert_eq!(fs::read(&path).expect("file must remain"), original_bytes);
    }

    #[test]
    fn short_secret_fails_without_replacing_the_file() {
        let directory = TestDirectory::new("short");
        let path = directory.secret_path();
        let original = format!(
            "{{\"version\":{SECRET_SCHEMA_VERSION},\"secret\":\"{}\"}}\n",
            "ab".repeat(MINIMUM_SECRET_BYTES - 1)
        );
        fs::write(&path, original.as_bytes()).expect("short secret must be written");

        let error = load_or_create_secret(&path).expect_err("short secret must fail");

        assert!(matches!(
            error,
            SecretError::TooShort {
                actual_bytes: 31,
                minimum_bytes: 32
            }
        ));
        assert_eq!(
            fs::read(&path).expect("file must remain"),
            original.as_bytes()
        );
    }

    #[test]
    fn unknown_version_fails_without_replacing_the_file() {
        let directory = TestDirectory::new("version");
        let path = directory.secret_path();
        let original = format!(
            "{{\"version\":{},\"secret\":\"{}\"}}\n",
            SECRET_SCHEMA_VERSION + 1,
            "ab".repeat(MINIMUM_SECRET_BYTES)
        );
        fs::write(&path, original.as_bytes()).expect("future secret must be written");

        let error = load_or_create_secret(&path).expect_err("unknown version must fail");

        assert!(matches!(
            error,
            SecretError::UnsupportedVersion { found: 2 }
        ));
        assert_eq!(
            fs::read(&path).expect("file must remain"),
            original.as_bytes()
        );
    }

    #[test]
    fn invalid_encoding_fails_without_replacing_the_file() {
        let directory = TestDirectory::new("encoding");
        let path = directory.secret_path();
        let original = format!(
            "{{\"version\":{SECRET_SCHEMA_VERSION},\"secret\":\"{}z\"}}\n",
            "ab".repeat(MINIMUM_SECRET_BYTES)
        );
        fs::write(&path, original.as_bytes()).expect("invalid secret must be written");

        let error = load_or_create_secret(&path).expect_err("invalid encoding must fail");

        assert!(matches!(error, SecretError::InvalidEncoding { .. }));
        assert_eq!(
            fs::read(&path).expect("file must remain"),
            original.as_bytes()
        );
    }
}
