use std::ffi::OsStr;
use std::io;
use std::iter;
use std::marker::PhantomData;
use std::os::windows::ffi::OsStrExt;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
use std::rc::Rc;
use std::sync::Arc;
use std::thread::{self, JoinHandle};

use windows_sys::Win32::Foundation::{
    ERROR_ALREADY_EXISTS, GetLastError, HANDLE, WAIT_ABANDONED_0, WAIT_FAILED, WAIT_OBJECT_0,
    WAIT_TIMEOUT,
};
use windows_sys::Win32::System::Threading::{
    CreateEventW, CreateMutexW, CreateSemaphoreW, INFINITE, ReleaseMutex, ReleaseSemaphore,
    SetEvent, WaitForMultipleObjects, WaitForSingleObject,
};

const MAX_KERNEL_OBJECT_NAME_UNITS: usize = 260;
const ACTIVATION_SEMAPHORE_LIMIT: i32 = i32::MAX;

#[derive(Debug)]
pub(crate) enum Acquisition {
    Primary(PrimaryInstance),
    Secondary,
}

#[derive(Debug)]
pub(crate) struct PrimaryInstance {
    mutex: Option<OwnedHandle>,
    activation_semaphore: Option<OwnedHandle>,
    owner_thread: PhantomData<Rc<()>>,
}

impl PrimaryInstance {
    fn new(mutex: OwnedHandle, activation_semaphore: OwnedHandle) -> Self {
        Self {
            mutex: Some(mutex),
            activation_semaphore: Some(activation_semaphore),
            owner_thread: PhantomData,
        }
    }

    pub(crate) fn start_listener<F>(&mut self, on_activation: F) -> io::Result<ActivationListener>
    where
        F: FnMut() -> io::Result<()> + Send + 'static,
    {
        let activation_semaphore = self.activation_semaphore.take().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                "single-instance activation listener already started",
            )
        })?;
        ActivationListener::start(activation_semaphore, on_activation)
    }

    pub(crate) fn release(mut self) -> io::Result<()> {
        let mutex = self.mutex.take().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                "single-instance mutex already released",
            )
        })?;
        if unsafe { ReleaseMutex(raw_handle(&mutex)) } == 0 {
            return Err(last_operation_error("ReleaseMutex(single-instance)"));
        }
        drop(mutex);
        Ok(())
    }
}

#[derive(Debug)]
pub(crate) struct ActivationListener {
    shutdown_event: Arc<OwnedHandle>,
    thread: JoinHandle<io::Result<()>>,
}

impl ActivationListener {
    fn start<F>(activation_semaphore: OwnedHandle, on_activation: F) -> io::Result<Self>
    where
        F: FnMut() -> io::Result<()> + Send + 'static,
    {
        let shutdown_event = Arc::new(create_shutdown_event()?);
        let thread_shutdown_event = Arc::clone(&shutdown_event);
        let thread = thread::Builder::new()
            .name("novwr-single-instance".to_string())
            .spawn(move || {
                listen_for_activations(
                    &activation_semaphore,
                    thread_shutdown_event.as_ref(),
                    on_activation,
                )
            })?;
        Ok(Self {
            shutdown_event,
            thread,
        })
    }

    pub(crate) fn shutdown(self) -> io::Result<()> {
        if unsafe { SetEvent(raw_handle(self.shutdown_event.as_ref())) } == 0 {
            return Err(last_operation_error("SetEvent(single-instance shutdown)"));
        }
        self.thread
            .join()
            .map_err(|_| io::Error::other("single-instance activation listener thread panicked"))?
    }
}

pub(crate) fn acquire(identifier: &str) -> io::Result<Acquisition> {
    let activation_name = kernel_object_name(identifier, "activation")?;
    let mutex_name = kernel_object_name(identifier, "mutex")?;

    // The semaphore is created first so duplicate activations can queue before the primary
    // process finishes building Tauri and attaches its listener.
    let activation_semaphore = create_activation_semaphore(&activation_name)?;
    let raw_mutex = unsafe { CreateMutexW(std::ptr::null(), 1, mutex_name.as_ptr()) };
    if raw_mutex.is_null() {
        return Err(last_operation_error("CreateMutexW(single-instance)"));
    }
    let mutex_already_existed = unsafe { GetLastError() } == ERROR_ALREADY_EXISTS;
    let mutex = unsafe { OwnedHandle::from_raw_handle(raw_mutex.cast()) };

    if !mutex_already_existed {
        return Ok(Acquisition::Primary(PrimaryInstance::new(
            mutex,
            activation_semaphore,
        )));
    }

    match unsafe { WaitForSingleObject(raw_handle(&mutex), 0) } {
        WAIT_OBJECT_0 => Ok(Acquisition::Primary(PrimaryInstance::new(
            mutex,
            activation_semaphore,
        ))),
        WAIT_ABANDONED_0 => Ok(Acquisition::Primary(PrimaryInstance::new(
            mutex,
            activation_semaphore,
        ))),
        WAIT_TIMEOUT => {
            if unsafe {
                ReleaseSemaphore(raw_handle(&activation_semaphore), 1, std::ptr::null_mut())
            } == 0
            {
                return Err(last_operation_error(
                    "ReleaseSemaphore(single-instance activation)",
                ));
            }
            drop((mutex, activation_semaphore));
            Ok(Acquisition::Secondary)
        }
        WAIT_FAILED => Err(last_operation_error("WaitForSingleObject(single-instance)")),
        result => Err(unexpected_wait_result(
            "WaitForSingleObject(single-instance)",
            result,
        )),
    }
}

fn listen_for_activations<F>(
    activation_semaphore: &OwnedHandle,
    shutdown_event: &OwnedHandle,
    mut on_activation: F,
) -> io::Result<()>
where
    F: FnMut() -> io::Result<()>,
{
    let handles = [raw_handle(shutdown_event), raw_handle(activation_semaphore)];
    loop {
        match unsafe { WaitForMultipleObjects(handles.len() as u32, handles.as_ptr(), 0, INFINITE) }
        {
            WAIT_OBJECT_0 => return Ok(()),
            result if result == WAIT_OBJECT_0 + 1 => on_activation()?,
            WAIT_FAILED => {
                return Err(last_operation_error(
                    "WaitForMultipleObjects(single-instance)",
                ));
            }
            result => {
                return Err(unexpected_wait_result(
                    "WaitForMultipleObjects(single-instance)",
                    result,
                ));
            }
        }
    }
}

fn create_activation_semaphore(name: &[u16]) -> io::Result<OwnedHandle> {
    let raw = unsafe {
        CreateSemaphoreW(
            std::ptr::null(),
            0,
            ACTIVATION_SEMAPHORE_LIMIT,
            name.as_ptr(),
        )
    };
    owned_handle(raw, "CreateSemaphoreW(single-instance activation)")
}

fn create_shutdown_event() -> io::Result<OwnedHandle> {
    let raw = unsafe { CreateEventW(std::ptr::null(), 1, 0, std::ptr::null()) };
    owned_handle(raw, "CreateEventW(single-instance shutdown)")
}

fn kernel_object_name(identifier: &str, kind: &str) -> io::Result<Vec<u16>> {
    if identifier.is_empty() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Tauri application identifier must not be empty",
        ));
    }
    if identifier.contains('\\') || identifier.contains('\0') {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Tauri application identifier is invalid for a Windows kernel object name",
        ));
    }

    let name = format!(r"Local\{identifier}.single-instance.{kind}");
    let encoded: Vec<u16> = OsStr::new(&name)
        .encode_wide()
        .chain(iter::once(0))
        .collect();
    if encoded.len() > MAX_KERNEL_OBJECT_NAME_UNITS {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Windows single-instance kernel object name exceeds MAX_PATH",
        ));
    }
    Ok(encoded)
}

fn owned_handle(raw: HANDLE, operation: &'static str) -> io::Result<OwnedHandle> {
    if raw.is_null() {
        Err(last_operation_error(operation))
    } else {
        Ok(unsafe { OwnedHandle::from_raw_handle(raw.cast()) })
    }
}

fn raw_handle(handle: &OwnedHandle) -> HANDLE {
    handle.as_raw_handle().cast()
}

fn last_operation_error(operation: &'static str) -> io::Error {
    let source = io::Error::from_raw_os_error(unsafe { GetLastError() } as i32);
    io::Error::new(source.kind(), format!("{operation}: {source}"))
}

fn unexpected_wait_result(operation: &'static str, result: u32) -> io::Error {
    io::Error::new(
        io::ErrorKind::InvalidData,
        format!("{operation} returned unexpected wait result {result:#010x}"),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;
    use std::fs;
    use std::path::{Path, PathBuf};
    use std::process::{self, Child, Command, ExitStatus};
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::mpsc;
    use std::time::{Duration, Instant};

    const HELPER_TEST: &str = "windows::single_instance::tests::single_instance_process_helper";
    const ROLE_ENV: &str = "NOVWR_SINGLE_INSTANCE_TEST_ROLE";
    const IDENTIFIER_ENV: &str = "NOVWR_SINGLE_INSTANCE_TEST_IDENTIFIER";
    const DIRECTORY_ENV: &str = "NOVWR_SINGLE_INSTANCE_TEST_DIRECTORY";
    const INDEX_ENV: &str = "NOVWR_SINGLE_INSTANCE_TEST_INDEX";
    const TOTAL_ENV: &str = "NOVWR_SINGLE_INSTANCE_TEST_TOTAL";
    const ABANDONED_EXIT_CODE: i32 = 73;
    const PROCESS_TIMEOUT: Duration = Duration::from_secs(10);
    static NEXT_IDENTIFIER: AtomicU64 = AtomicU64::new(1);
    static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(1);

    struct TestDirectory {
        path: PathBuf,
    }

    impl TestDirectory {
        fn new(label: &str) -> Self {
            let path = env::temp_dir().join(format!(
                "novwr-single-instance-{label}-{}-{}",
                process::id(),
                NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).expect("create single-instance test directory");
            Self { path }
        }

        fn path(&self) -> &Path {
            &self.path
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }

    #[test]
    fn delayed_listener_receives_queued_secondary_activation() {
        let directory = TestDirectory::new("delayed");
        let identifier = unique_identifier("delayed");
        let mut primary = expect_primary(acquire(&identifier));
        let result_path = directory.path().join("secondary-result");

        let child = helper_command("secondary", &identifier, directory.path())
            .env("NOVWR_SINGLE_INSTANCE_TEST_RESULT", &result_path)
            .spawn()
            .expect("spawn delayed-listener secondary helper");
        let statuses = wait_for_children(vec![child]);
        assert!(statuses[0].success(), "secondary helper failed");
        assert_eq!(
            fs::read_to_string(&result_path).expect("read secondary helper result"),
            "secondary"
        );

        let (activation_tx, activation_rx) = mpsc::channel();
        let listener = primary
            .start_listener(move || {
                activation_tx
                    .send(())
                    .map_err(|error| io::Error::other(error.to_string()))
            })
            .expect("start delayed activation listener");
        activation_rx
            .recv_timeout(Duration::from_secs(2))
            .expect("queued activation was not delivered");

        listener
            .shutdown()
            .expect("stop delayed activation listener");
        primary.release().expect("release delayed test mutex");
    }

    #[test]
    fn abandoned_mutex_promotes_the_next_process_to_primary() {
        let directory = TestDirectory::new("abandoned");
        let identifier = unique_identifier("abandoned");
        let ready_path = directory.path().join("abandoned-ready");
        let continue_path = directory.path().join("abandoned-continue");

        let child = helper_command("abandon-primary", &identifier, directory.path())
            .spawn()
            .expect("spawn abandoned primary helper");
        assert!(
            wait_for_path(&ready_path, PROCESS_TIMEOUT),
            "abandoned primary helper never acquired the mutex"
        );
        // Keep the kernel object alive after the owning process exits so the next acquire must
        // handle WAIT_ABANDONED_0 instead of creating a fresh mutex.
        let mutex_keepalive = open_existing_mutex(&identifier);
        fs::write(&continue_path, b"exit").expect("release abandoned primary helper");

        let statuses = wait_for_children(vec![child]);
        assert_eq!(statuses[0].code(), Some(ABANDONED_EXIT_CODE));

        let primary = expect_primary(acquire(&identifier));
        primary
            .release()
            .expect("release recovered abandoned mutex");
        drop(mutex_keepalive);
    }

    #[test]
    fn concurrent_processes_elect_one_primary_and_preserve_every_activation() {
        const PROCESS_COUNT: usize = 6;

        let directory = TestDirectory::new("concurrent");
        let identifier = unique_identifier("concurrent");
        let mut children = Vec::with_capacity(PROCESS_COUNT);
        for index in 0..PROCESS_COUNT {
            children.push(
                helper_command("race", &identifier, directory.path())
                    .env(INDEX_ENV, index.to_string())
                    .env(TOTAL_ENV, PROCESS_COUNT.to_string())
                    .spawn()
                    .expect("spawn concurrent single-instance helper"),
            );
        }

        for index in 0..PROCESS_COUNT {
            assert!(
                wait_for_path(
                    &directory.path().join(format!("ready-{index}")),
                    PROCESS_TIMEOUT,
                ),
                "concurrent helper {index} did not become ready"
            );
        }
        fs::write(directory.path().join("start"), b"start").expect("release concurrent helpers");

        let statuses = wait_for_children(children);
        assert!(
            statuses.iter().all(ExitStatus::success),
            "one or more concurrent helpers failed: {statuses:?}"
        );

        let mut primary_indexes = Vec::new();
        let mut secondary_count = 0;
        for index in 0..PROCESS_COUNT {
            match fs::read_to_string(directory.path().join(format!("result-{index}")))
                .expect("read concurrent helper result")
                .as_str()
            {
                "primary" => primary_indexes.push(index),
                "secondary" => secondary_count += 1,
                result => panic!("unexpected concurrent helper result {result:?}"),
            }
        }
        assert_eq!(primary_indexes.len(), 1, "exactly one process must win");
        assert_eq!(secondary_count, PROCESS_COUNT - 1);

        let activation_count = fs::read_to_string(
            directory
                .path()
                .join(format!("activations-{}", primary_indexes[0])),
        )
        .expect("read primary activation count")
        .parse::<usize>()
        .expect("parse primary activation count");
        assert_eq!(activation_count, PROCESS_COUNT - 1);
    }

    #[test]
    fn single_instance_process_helper() {
        let Some(role) = env::var_os(ROLE_ENV) else {
            return;
        };
        let role = role.to_string_lossy();
        let identifier = env::var(IDENTIFIER_ENV).expect("helper identifier is required");
        let directory = PathBuf::from(
            env::var_os(DIRECTORY_ENV).expect("helper coordination directory is required"),
        );

        match role.as_ref() {
            "secondary" => {
                assert!(matches!(
                    acquire(&identifier).expect("secondary helper acquisition failed"),
                    Acquisition::Secondary
                ));
                let result_path = PathBuf::from(
                    env::var_os("NOVWR_SINGLE_INSTANCE_TEST_RESULT")
                        .expect("secondary helper result path is required"),
                );
                fs::write(result_path, b"secondary").expect("write secondary helper result");
            }
            "abandon-primary" => {
                let _primary = expect_primary(acquire(&identifier));
                fs::write(directory.join("abandoned-ready"), b"ready")
                    .expect("write abandoned helper ready marker");
                assert!(
                    wait_for_path(&directory.join("abandoned-continue"), PROCESS_TIMEOUT),
                    "parent never released abandoned primary helper"
                );
                process::exit(ABANDONED_EXIT_CODE);
            }
            "race" => run_race_helper(&identifier, &directory),
            other => panic!("unknown single-instance helper role {other:?}"),
        }
    }

    fn run_race_helper(identifier: &str, directory: &Path) {
        let index = env::var(INDEX_ENV)
            .expect("race helper index is required")
            .parse::<usize>()
            .expect("race helper index must be numeric");
        let total = env::var(TOTAL_ENV)
            .expect("race helper total is required")
            .parse::<usize>()
            .expect("race helper total must be numeric");
        fs::write(directory.join(format!("ready-{index}")), b"ready")
            .expect("write race helper ready marker");
        assert!(
            wait_for_path(&directory.join("start"), PROCESS_TIMEOUT),
            "parent never released race helper"
        );

        match acquire(identifier).expect("race helper acquisition failed") {
            Acquisition::Secondary => {
                fs::write(directory.join(format!("result-{index}")), b"secondary")
                    .expect("write race secondary result");
            }
            Acquisition::Primary(mut primary) => {
                fs::write(directory.join(format!("result-{index}")), b"primary")
                    .expect("write race primary result");

                // Force secondaries to signal before the listener exists. The semaphore must
                // preserve all activations across this cold-start interval.
                thread::sleep(Duration::from_millis(200));
                let (activation_tx, activation_rx) = mpsc::channel();
                let listener = primary
                    .start_listener(move || {
                        activation_tx
                            .send(())
                            .map_err(|error| io::Error::other(error.to_string()))
                    })
                    .expect("start race primary listener");

                let expected = total - 1;
                let deadline = Instant::now() + PROCESS_TIMEOUT;
                let mut activation_count = 0;
                while activation_count < expected {
                    let remaining = deadline.saturating_duration_since(Instant::now());
                    activation_rx
                        .recv_timeout(remaining)
                        .expect("race primary did not receive every activation");
                    activation_count += 1;
                }
                fs::write(
                    directory.join(format!("activations-{index}")),
                    activation_count.to_string(),
                )
                .expect("write race activation count");
                listener.shutdown().expect("stop race primary listener");
                primary.release().expect("release race primary mutex");
            }
        }
    }

    fn helper_command(role: &str, identifier: &str, directory: &Path) -> Command {
        let mut command = Command::new(env::current_exe().expect("resolve test executable"));
        command
            .args(["--exact", HELPER_TEST, "--nocapture"])
            .env(ROLE_ENV, role)
            .env(IDENTIFIER_ENV, identifier)
            .env(DIRECTORY_ENV, directory);
        command
    }

    fn expect_primary(acquisition: io::Result<Acquisition>) -> PrimaryInstance {
        match acquisition.expect("single-instance acquisition failed") {
            Acquisition::Primary(primary) => primary,
            Acquisition::Secondary => panic!("expected primary single-instance acquisition"),
        }
    }

    fn open_existing_mutex(identifier: &str) -> OwnedHandle {
        let name = kernel_object_name(identifier, "mutex").expect("build test mutex name");
        let raw = unsafe { CreateMutexW(std::ptr::null(), 0, name.as_ptr()) };
        assert!(!raw.is_null(), "open existing test mutex failed");
        assert_eq!(unsafe { GetLastError() }, ERROR_ALREADY_EXISTS);
        unsafe { OwnedHandle::from_raw_handle(raw.cast()) }
    }

    fn unique_identifier(label: &str) -> String {
        format!(
            "io.github.hurricane0698.novwr.test.{label}.{}.{}",
            process::id(),
            NEXT_IDENTIFIER.fetch_add(1, Ordering::Relaxed)
        )
    }

    fn wait_for_path(path: &Path, timeout: Duration) -> bool {
        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            if path.exists() {
                return true;
            }
            thread::sleep(Duration::from_millis(10));
        }
        path.exists()
    }

    fn wait_for_children(mut children: Vec<Child>) -> Vec<ExitStatus> {
        let deadline = Instant::now() + PROCESS_TIMEOUT;
        let mut statuses: Vec<Option<ExitStatus>> =
            iter::repeat_with(|| None).take(children.len()).collect();

        while statuses.iter().any(Option::is_none) && Instant::now() < deadline {
            for (child, status) in children.iter_mut().zip(&mut statuses) {
                if status.is_none() {
                    *status = child.try_wait().expect("poll helper process");
                }
            }
            thread::sleep(Duration::from_millis(10));
        }

        if statuses.iter().any(Option::is_none) {
            for (child, status) in children.iter_mut().zip(&mut statuses) {
                if status.is_none() {
                    let _ = child.kill();
                    *status = Some(child.wait().expect("reap timed-out helper process"));
                }
            }
            panic!("single-instance helper process exceeded {PROCESS_TIMEOUT:?}");
        }

        statuses
            .into_iter()
            .map(|status| status.expect("helper status must be populated"))
            .collect()
    }
}
