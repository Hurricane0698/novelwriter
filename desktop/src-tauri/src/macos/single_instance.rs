//! Per-user flock ownership and queued activation datagrams. A crashed primary
//! releases the kernel lock; only the next lock owner removes a stale socket.

use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::AsRawFd;
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::net::UnixDatagram;
use std::path::PathBuf;
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

#[derive(Debug)]
pub(crate) enum Acquisition {
    Primary(PrimaryInstance),
    Secondary,
}

#[derive(Debug)]
pub(crate) struct PrimaryInstance {
    lock: Option<File>,
    activation: Option<UnixDatagram>,
    socket_path: PathBuf,
}

impl PrimaryInstance {
    pub(crate) fn start_listener<F>(
        &mut self,
        mut on_activation: F,
    ) -> io::Result<ActivationListener>
    where
        F: FnMut() -> io::Result<()> + Send + 'static,
    {
        let activation = self.activation.take().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                "single-instance listener already started",
            )
        })?;
        let (shutdown, stop) = UnixDatagram::pair()?;
        let thread = thread::Builder::new()
            .name("novwr-single-instance".into())
            .spawn(move || {
                let mut descriptors = [
                    libc::pollfd {
                        fd: stop.as_raw_fd(),
                        events: libc::POLLIN,
                        revents: 0,
                    },
                    libc::pollfd {
                        fd: activation.as_raw_fd(),
                        events: libc::POLLIN,
                        revents: 0,
                    },
                ];
                loop {
                    let result = unsafe { libc::poll(descriptors.as_mut_ptr(), 2, -1) };
                    if result < 0 {
                        let error = io::Error::last_os_error();
                        if error.kind() == io::ErrorKind::Interrupted {
                            continue;
                        }
                        return Err(error);
                    }
                    if descriptors[0].revents != 0 {
                        return Ok(());
                    }
                    if descriptors[1].revents != 0 {
                        let mut message = [0; 8];
                        let count = activation.recv(&mut message)?;
                        if &message[..count] == b"activate" {
                            on_activation()?;
                        }
                    }
                }
            })?;
        Ok(ActivationListener { shutdown, thread })
    }

    pub(crate) fn release(mut self) -> io::Result<()> {
        self.activation.take();
        match fs::remove_file(&self.socket_path) {
            Ok(()) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
        // Close, rather than unlink, the locked file: unlinking creates two
        // independent lock domains when a secondary already has the old inode.
        self.lock.take();
        Ok(())
    }
}

#[derive(Debug)]
pub(crate) struct ActivationListener {
    shutdown: UnixDatagram,
    thread: JoinHandle<io::Result<()>>,
}

impl ActivationListener {
    pub(crate) fn shutdown(self) -> io::Result<()> {
        self.shutdown.send(b"stop")?;
        self.thread
            .join()
            .map_err(|_| io::Error::other("single-instance listener panicked"))?
    }
}

pub(crate) fn acquire(identifier: &str) -> io::Result<Acquisition> {
    let directory = instance_directory(identifier)?;
    let socket_path = directory.join("activation.sock");
    let lock = OpenOptions::new()
        .create(true)
        .read(true)
        .write(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(directory.join("instance.lock"))?;
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0 {
            match fs::remove_file(&socket_path) {
                Ok(()) => {}
                Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                Err(error) => return Err(error),
            }
            let activation = UnixDatagram::bind(&socket_path)?;
            fs::set_permissions(&socket_path, fs::Permissions::from_mode(0o600))?;
            return Ok(Acquisition::Primary(PrimaryInstance {
                lock: Some(lock),
                activation: Some(activation),
                socket_path,
            }));
        }
        let error = io::Error::last_os_error();
        if error.raw_os_error() != Some(libc::EWOULDBLOCK) {
            return Err(error);
        }
        let sender = UnixDatagram::unbound()?;
        sender.set_write_timeout(Some(Duration::from_millis(250)))?;
        match sender.send_to(b"activate", &socket_path) {
            Ok(_) => return Ok(Acquisition::Secondary),
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::NotFound
                        | io::ErrorKind::ConnectionRefused
                        | io::ErrorKind::WouldBlock
                        | io::ErrorKind::TimedOut
                ) && Instant::now() < deadline =>
            {
                // A first launch may own the lock before binding its socket.
                // Retry the lock too, so a crashed first launch is recoverable.
                thread::sleep(Duration::from_millis(20));
            }
            Err(error) => return Err(error),
        }
    }
}

fn instance_directory(identifier: &str) -> io::Result<PathBuf> {
    if identifier.is_empty()
        || !identifier
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b".-_".contains(&byte))
        || identifier.len() > 180
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid application identifier",
        ));
    }
    // A short, deterministic path fits macOS sockaddr_un even for long app IDs.
    let hash = identifier
        .bytes()
        .fold(0xcbf29ce484222325_u64, |hash, byte| {
            (hash ^ u64::from(byte)).wrapping_mul(0x100000001b3)
        });
    let uid = unsafe { libc::geteuid() };
    let directory = PathBuf::from(format!("/tmp/novwr-{uid}-{hash:016x}"));
    match fs::DirBuilder::new().mode(0o700).create(&directory) {
        Ok(()) => {}
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
        Err(error) => return Err(error),
    }
    let metadata = fs::symlink_metadata(&directory)?;
    if !metadata.is_dir() || metadata.uid() != uid || metadata.mode() & 0o077 != 0 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "single-instance directory must be private and owned by this user",
        ));
    }
    Ok(directory)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::process::ExitStatusExt;
    use std::process::{Command, Stdio};
    use std::sync::mpsc;

    fn identifier() -> String {
        format!(
            "novwr.test.{}.{}",
            std::process::id(),
            getrandom::u64().unwrap()
        )
    }

    #[test]
    fn secondary_activations_queue_before_listener_starts() {
        let id = identifier();
        let Acquisition::Primary(mut primary) = acquire(&id).unwrap() else {
            panic!("first launch must own lock")
        };
        assert!(matches!(acquire(&id).unwrap(), Acquisition::Secondary));
        assert!(matches!(acquire(&id).unwrap(), Acquisition::Secondary));
        let (sent, received) = mpsc::channel();
        let listener = primary
            .start_listener(move || {
                sent.send(()).unwrap();
                Ok(())
            })
            .unwrap();
        received.recv_timeout(Duration::from_secs(2)).unwrap();
        received.recv_timeout(Duration::from_secs(2)).unwrap();
        listener.shutdown().unwrap();
        primary.release().unwrap();
        fs::remove_dir_all(instance_directory(&id).unwrap()).unwrap();
    }

    #[test]
    fn primary_subprocess() {
        let Ok(id) = std::env::var("NOVWR_TEST_INSTANCE_IDENTIFIER") else {
            return;
        };
        let Acquisition::Primary(_primary) = acquire(&id).unwrap() else {
            panic!("isolated child must own lock")
        };
        fs::write(
            std::env::var_os("NOVWR_TEST_INSTANCE_READY").unwrap(),
            b"ready",
        )
        .unwrap();
        loop {
            thread::sleep(Duration::from_secs(60));
        }
    }

    #[test]
    fn abandoned_socket_does_not_prevent_a_new_primary() {
        let id = identifier();
        let directory = tempfile::tempdir().unwrap();
        let ready = directory.path().join("ready");
        // The owner must be a separate process: concurrent spawn/exec in this
        // test harness can briefly inherit a CLOEXEC flock descriptor, so an
        // in-process drop does not model the end of an actual app process.
        let mut owner = Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "macos::single_instance::tests::primary_subprocess",
                "--nocapture",
            ])
            .env("NOVWR_TEST_INSTANCE_IDENTIFIER", &id)
            .env("NOVWR_TEST_INSTANCE_READY", &ready)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        while !ready.exists() && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(10));
        }
        let started = ready.exists();
        // Reap on the timeout path too; test failures must not leave helpers.
        owner.kill().unwrap();
        let status = owner.wait().unwrap();
        assert!(started, "isolated primary did not become ready");
        assert_eq!(status.signal(), Some(libc::SIGKILL));
        let Acquisition::Primary(primary) = acquire(&id).unwrap() else {
            panic!("reclaimed primary")
        };
        primary.release().unwrap();
        fs::remove_dir_all(instance_directory(&id).unwrap()).unwrap();
    }
}
