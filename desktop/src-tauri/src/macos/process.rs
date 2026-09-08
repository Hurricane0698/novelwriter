//! A guardian owns each child group. The app alone owns its control-pipe writer;
//! EOF therefore reclaims children even after SIGKILL, without relying on Drop.

use std::ffi::OsString;
use std::fs::{File, OpenOptions};
use std::io::{self, BufRead, BufReader, Write};
use std::os::fd::{AsRawFd, RawFd};
use std::os::unix::fs::OpenOptionsExt;
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, ExitStatus, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

pub const DEFAULT_TERMINATION_EXIT_CODE: u32 = 1;
const GUARDIAN_ARGUMENT: &str = "--novwr-process-guardian";
const SHUTDOWN_FD_ENV: &str = "NOVWR_DESKTOP_SHUTDOWN_FD";
const READY_TIMEOUT: Duration = Duration::from_secs(10);
const POLL_INTERVAL: Duration = Duration::from_millis(20);

#[derive(Clone, Debug, Default)]
pub struct EnvironmentDelta {
    removals: Vec<OsString>,
    additions: Vec<(OsString, OsString)>,
}

impl EnvironmentDelta {
    pub fn new() -> Self {
        Self::default()
    }
    pub fn remove(&mut self, name: impl Into<OsString>) {
        self.removals.push(name.into());
    }
    pub fn set(&mut self, name: impl Into<OsString>, value: impl Into<OsString>) {
        self.additions.push((name.into(), value.into()));
    }
    pub fn with_set(mut self, name: impl Into<OsString>, value: impl Into<OsString>) -> Self {
        self.set(name, value);
        self
    }
}

#[derive(Clone, Debug)]
pub struct ProcessCommand {
    executable: PathBuf,
    arguments: Vec<OsString>,
    current_directory: PathBuf,
    stdout_path: PathBuf,
    stderr_path: PathBuf,
    environment: EnvironmentDelta,
}

impl ProcessCommand {
    pub fn new(
        executable: impl Into<PathBuf>,
        current_directory: impl Into<PathBuf>,
        stdout_path: impl Into<PathBuf>,
        stderr_path: impl Into<PathBuf>,
    ) -> Self {
        Self {
            executable: executable.into(),
            arguments: Vec::new(),
            current_directory: current_directory.into(),
            stdout_path: stdout_path.into(),
            stderr_path: stderr_path.into(),
            environment: EnvironmentDelta::new(),
        }
    }
    pub fn arg(mut self, argument: impl Into<OsString>) -> Self {
        self.arguments.push(argument.into());
        self
    }
    pub fn environment(mut self, environment: EnvironmentDelta) -> Self {
        self.environment = environment;
        self
    }
}

#[derive(Debug)]
struct ProcessState {
    guardian: Mutex<Child>,
    control: Mutex<Option<ChildStdin>>,
    process_id: u32,
}

impl ProcessState {
    fn send(&self, command: u8) -> io::Result<()> {
        let mut control = self
            .control
            .lock()
            .map_err(|_| io::Error::other("guardian control mutex poisoned"))?;
        if let Some(pipe) = control.as_mut() {
            match pipe.write_all(&[command]) {
                Ok(()) => Ok(()),
                Err(error) if error.kind() == io::ErrorKind::BrokenPipe => {
                    control.take();
                    Ok(())
                }
                Err(error) => Err(error),
            }
        } else {
            Ok(())
        }
    }
    fn exit_code(&self) -> io::Result<Option<u32>> {
        self.guardian
            .lock()
            .map_err(|_| io::Error::other("guardian process mutex poisoned"))?
            .try_wait()
            .map(|status| status.map(exit_code))
    }
}

type Processes = Arc<Mutex<Vec<Arc<ProcessState>>>>;

#[derive(Debug, Default)]
pub struct JobObject {
    processes: Processes,
}

impl JobObject {
    pub fn new() -> io::Result<Self> {
        Ok(Self::default())
    }

    pub fn spawn(&self, command: &ProcessCommand) -> io::Result<ManagedProcess> {
        for path in [
            &command.executable,
            &command.current_directory,
            &command.stdout_path,
            &command.stderr_path,
        ] {
            if !path.is_absolute() {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "runtime process paths must be absolute",
                ));
            }
        }
        let mut guardian = guardian_command(command)?;
        // Isolate the guardian from signals sent to the app's process group.
        guardian
            .process_group(0)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(open_log(&command.stderr_path)?);
        for name in &command.environment.removals {
            guardian.env_remove(name);
        }
        for (name, value) in &command.environment.additions {
            guardian.env(name, value);
        }
        let mut child = guardian.spawn()?;
        let mut control = child
            .stdin
            .take()
            .ok_or_else(|| io::Error::other("guardian has no control pipe"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| io::Error::other("guardian has no readiness pipe"))?;
        // The child is not allowed to run until its guardian owns the group. A
        // bounded handshake also reports exec errors without accepting a zombie.
        let ready = (|| {
            if !readable(stdout.as_raw_fd(), READY_TIMEOUT)? {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "guardian startup timed out",
                ));
            }
            let mut reader = BufReader::new(stdout);
            let mut line = String::new();
            // The production entry prints only READY. Cargo's helper entry also
            // prints a short test-harness preamble before reaching that code.
            for _ in 0..8 {
                line.clear();
                if reader.read_line(&mut line)? == 0 {
                    break;
                }
                if let Some(pid) = line
                    .strip_prefix("READY ")
                    .and_then(|pid| pid.trim().parse::<u32>().ok())
                {
                    return Ok(pid);
                }
            }
            Err(io::Error::other("guardian failed to start runtime process"))
        })();
        let process_id = match ready {
            Ok(pid) => pid,
            Err(error) => {
                let _ = control.write_all(b"K");
                drop(control);
                // EOF is a kill request even if readiness failed; the guardian
                // is already live and always reaps any child it managed to start.
                let _ = child.wait();
                return Err(error);
            }
        };
        let state = Arc::new(ProcessState {
            guardian: Mutex::new(child),
            control: Mutex::new(Some(control)),
            process_id,
        });
        self.processes
            .lock()
            .map_err(|_| io::Error::other("process group mutex poisoned"))?
            .push(Arc::clone(&state));
        Ok(ManagedProcess { state })
    }

    pub fn terminate(&self, _exit_code: u32) -> io::Result<()> {
        let processes = self
            .processes
            .lock()
            .map_err(|_| io::Error::other("process group mutex poisoned"))?;
        let mut failure = None;
        for process in processes.iter() {
            if let Err(error) = process.send(b'K') {
                failure.get_or_insert(error);
            }
        }
        failure.map_or(Ok(()), Err)
    }

    pub fn terminate_and_wait(
        &self,
        processes: &[&ManagedProcess],
        exit_code: u32,
        timeout: Duration,
    ) -> io::Result<()> {
        self.terminate(exit_code)?;
        let started = Instant::now();
        for process in processes {
            if process
                .wait_for_exit(timeout.saturating_sub(started.elapsed()))?
                .is_none()
            {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "runtime group did not exit after termination",
                ));
            }
        }
        Ok(())
    }
}

impl Drop for JobObject {
    fn drop(&mut self) {
        let _ = self.terminate(DEFAULT_TERMINATION_EXIT_CODE);
        if let Ok(processes) = self.processes.lock() {
            for process in processes.iter() {
                // Dropping the only app-side writer is the guardian's fail-safe.
                if let Ok(mut control) = process.control.lock() {
                    control.take();
                }
                if let Ok(mut guardian) = process.guardian.lock() {
                    let _ = guardian.wait();
                }
            }
        }
    }
}

#[derive(Debug)]
pub struct ShutdownEvent {
    processes: Processes,
}

impl ShutdownEvent {
    pub fn create(job: &JobObject) -> io::Result<Self> {
        Ok(Self {
            processes: Arc::clone(&job.processes),
        })
    }
    pub fn signal(&self) -> io::Result<()> {
        let processes = self
            .processes
            .lock()
            .map_err(|_| io::Error::other("process group mutex poisoned"))?;
        for process in processes.iter() {
            process.send(b'G')?;
        }
        Ok(())
    }
}

#[derive(Debug)]
#[must_use = "the owning JobObject controls the runtime process lifetime"]
pub struct ManagedProcess {
    state: Arc<ProcessState>,
}

impl ManagedProcess {
    pub fn id(&self) -> u32 {
        self.state.process_id
    }
    pub fn is_running(&self) -> io::Result<bool> {
        self.state.exit_code().map(|status| status.is_none())
    }
    pub fn exit_code(&self) -> io::Result<Option<u32>> {
        self.state.exit_code()
    }
    pub fn wait_for_exit(&self, timeout: Duration) -> io::Result<Option<u32>> {
        let started = Instant::now();
        loop {
            if let Some(code) = self.exit_code()? {
                return Ok(Some(code));
            }
            if started.elapsed() >= timeout {
                return Ok(None);
            }
            thread::sleep(POLL_INTERVAL.min(timeout.saturating_sub(started.elapsed())));
        }
    }
    pub fn wait_for_success(&self, timeout: Duration) -> io::Result<()> {
        match self.wait_for_exit(timeout)? {
            Some(0) => Ok(()),
            Some(code) => Err(io::Error::other(format!(
                "process {} exited with code {code}",
                self.id()
            ))),
            None => Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!("process {} did not exit within {timeout:?}", self.id()),
            )),
        }
    }
}

fn guardian_arguments(command: &ProcessCommand) -> Vec<OsString> {
    let mut args = vec![
        GUARDIAN_ARGUMENT.into(),
        command.executable.clone().into(),
        command.current_directory.clone().into(),
        command.stdout_path.clone().into(),
        command.stderr_path.clone().into(),
    ];
    args.extend(command.arguments.iter().cloned());
    args
}

fn guardian_command(command: &ProcessCommand) -> io::Result<Command> {
    let mut child = Command::new(std::env::current_exe()?);
    #[cfg(not(test))]
    child.args(guardian_arguments(command));
    #[cfg(test)]
    {
        // Cargo's test executable has a harness entrypoint; enter the exact
        // helper test before dispatching the same production guardian function.
        child.args([
            "--exact",
            "macos::process::tests::guardian_subprocess",
            "--nocapture",
        ]);
        let args: Vec<String> = guardian_arguments(command)
            .iter()
            .map(|arg| arg.to_string_lossy().into_owned())
            .collect();
        child.env(
            "NOVWR_TEST_GUARDIAN_ARGUMENTS",
            serde_json::to_string(&args)?,
        );
    }
    Ok(child)
}

pub fn run_guardian_if_requested() -> Option<i32> {
    let mut args = std::env::args_os().skip(1);
    if args.next()?.as_os_str() != GUARDIAN_ARGUMENT {
        return None;
    }
    Some(match run_guardian(args.collect()) {
        Ok(code) => code as i32,
        Err(error) => {
            eprintln!("NovWr process guardian: {error}");
            1
        }
    })
}

struct GuardedChild {
    child: Option<Child>,
    group: libc::pid_t,
}

impl GuardedChild {
    fn finish(&mut self) -> io::Result<ExitStatus> {
        kill_group(self.group)?;
        let status = self.child.as_mut().expect("owned runtime child").wait()?;
        self.child.take();
        Ok(status)
    }
}
impl Drop for GuardedChild {
    fn drop(&mut self) {
        if self.child.is_some() {
            let _ = self.finish();
        }
    }
}

fn run_guardian(args: Vec<OsString>) -> io::Result<u32> {
    if args.len() < 4 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid guardian arguments",
        ));
    }
    let mut backend = Command::new(&args[0]);
    backend
        .current_dir(&args[1])
        .args(&args[4..])
        .process_group(0)
        .stdin(Stdio::piped())
        .stdout(open_log(&PathBuf::from(&args[2]))?)
        .stderr(open_log(&PathBuf::from(&args[3]))?)
        .env(SHUTDOWN_FD_ENV, "0");
    let mut child = backend.spawn()?;
    let mut shutdown = child
        .stdin
        .take()
        .ok_or_else(|| io::Error::other("runtime child has no shutdown pipe"))?;
    let group = child.id() as libc::pid_t;
    let mut owned = GuardedChild {
        child: Some(child),
        group,
    };
    writeln!(io::stdout(), "READY {group}")?;
    io::stdout().flush()?;
    let mut graceful = false;
    loop {
        // WNOWAIT keeps the leader PID reserved until descendants are killed,
        // so a reused PID can never redirect group cleanup to an unrelated job.
        if child_has_exited(group)? {
            return owned.finish().map(exit_code);
        }
        if !readable(0, POLL_INTERVAL)? {
            continue;
        }
        let mut byte = [0];
        // Read the raw descriptor: buffered stdin could prefetch a following K
        // while handling G, leaving poll unable to see the buffered command.
        let count = unsafe { libc::read(0, byte.as_mut_ptr().cast(), 1) };
        let read = if count < 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(count)
        };
        match read {
            Ok(0) => return owned.finish().map(exit_code),
            Ok(_) if byte[0] == b'K' => return owned.finish().map(exit_code),
            Ok(_) if byte[0] == b'G' && !graceful => {
                graceful = true;
                if let Err(error) = shutdown.write_all(b"S") {
                    if error.kind() != io::ErrorKind::BrokenPipe {
                        return Err(error);
                    }
                }
            }
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(error) => return Err(error),
        }
    }
}

fn child_has_exited(pid: libc::pid_t) -> io::Result<bool> {
    let mut info = std::mem::MaybeUninit::<libc::siginfo_t>::zeroed();
    let result = unsafe {
        libc::waitid(
            libc::P_PID,
            pid as libc::id_t,
            info.as_mut_ptr(),
            libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
        )
    };
    if result < 0 {
        return Err(io::Error::last_os_error());
    }
    let info = unsafe { info.assume_init() };
    Ok(info.si_pid == pid)
}

fn kill_group(group: libc::pid_t) -> io::Result<()> {
    if unsafe { libc::kill(-group, libc::SIGKILL) } == 0 {
        return Ok(());
    }
    let error = io::Error::last_os_error();
    if error.raw_os_error() == Some(libc::ESRCH) {
        return Ok(());
    }
    // Darwin reports EPERM for a group containing only an unsignalable zombie.
    // We still own that unreaped leader; live descendants remain signalable by
    // this same-user guardian. Preserve the original exit status in this case.
    if error.raw_os_error() == Some(libc::EPERM) && child_has_exited(group)? {
        return Ok(());
    }
    Err(error)
}

fn readable(fd: RawFd, timeout: Duration) -> io::Result<bool> {
    let mut descriptor = libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    };
    let result = unsafe {
        libc::poll(
            &mut descriptor,
            1,
            timeout.as_millis().min(i32::MAX as u128) as i32,
        )
    };
    if result < 0 {
        let error = io::Error::last_os_error();
        if error.kind() == io::ErrorKind::Interrupted {
            return Ok(false);
        }
        return Err(error);
    }
    Ok(result > 0)
}

fn open_log(path: &PathBuf) -> io::Result<File> {
    OpenOptions::new()
        .create(true)
        .append(true)
        .mode(0o600)
        .open(path)
}
fn exit_code(status: ExitStatus) -> u32 {
    status
        .code()
        .unwrap_or_else(|| 128 + status.signal().unwrap_or(1)) as u32
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::Path;

    #[test]
    fn guardian_subprocess() {
        let Ok(payload) = std::env::var("NOVWR_TEST_GUARDIAN_ARGUMENTS") else {
            return;
        };
        let mut args: Vec<OsString> = serde_json::from_str::<Vec<String>>(&payload)
            .unwrap()
            .into_iter()
            .map(OsString::from)
            .collect();
        args.remove(0);
        std::process::exit(match run_guardian(args) {
            Ok(code) => code as i32,
            Err(error) => {
                eprintln!("{error}");
                1
            }
        });
    }

    fn shell(directory: &Path, script: &str) -> ProcessCommand {
        ProcessCommand::new(
            "/bin/sh",
            directory,
            directory.join("stdout.log"),
            directory.join("stderr.log"),
        )
        .arg("-c")
        .arg(script)
    }

    fn wait_file(path: &Path) -> String {
        let started = Instant::now();
        while started.elapsed() < Duration::from_secs(10) {
            if let Ok(value) = fs::read_to_string(path) {
                if !value.trim().is_empty() {
                    return value;
                }
            }
            thread::sleep(POLL_INTERVAL);
        }
        panic!("did not receive file {}", path.display());
    }

    fn wait_gone(pid: u32) {
        let started = Instant::now();
        while started.elapsed() < Duration::from_secs(5) {
            if unsafe { libc::kill(pid as i32, 0) } < 0
                && io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH)
            {
                return;
            }
            thread::sleep(POLL_INTERVAL);
        }
        panic!("process {pid} was not reclaimed");
    }

    #[test]
    fn graceful_shutdown_allows_current_work_to_finish() {
        let directory = tempfile::tempdir().unwrap();
        let job = JobObject::new().unwrap();
        let process = job
            .spawn(&shell(
                directory.path(),
                "dd bs=1 count=1 of=signal 2>/dev/null; sleep 0.15; echo done > finished",
            ))
            .unwrap();
        ShutdownEvent::create(&job).unwrap().signal().unwrap();
        assert_eq!(
            process.wait_for_exit(Duration::from_secs(3)).unwrap(),
            Some(0),
            "{}",
            fs::read_to_string(directory.path().join("stderr.log")).unwrap()
        );
        assert_eq!(fs::read(directory.path().join("signal")).unwrap(), b"S");
        assert_eq!(
            fs::read_to_string(directory.path().join("finished"))
                .unwrap()
                .trim(),
            "done"
        );
        wait_gone(process.id());
    }

    #[test]
    fn force_after_graceful_command_kills_group_without_waiting_for_eof() {
        let directory = tempfile::tempdir().unwrap();
        let job = JobObject::new().unwrap();
        let process = job
            .spawn(&shell(
                directory.path(),
                "sleep 60 & echo $! > grandchild; wait",
            ))
            .unwrap();
        let grandchild: u32 = wait_file(&directory.path().join("grandchild"))
            .trim()
            .parse()
            .unwrap();
        // Send both commands together to catch buffered stdin consuming K while
        // poll observes an empty kernel pipe. Keep the app writer open.
        process
            .state
            .control
            .lock()
            .unwrap()
            .as_mut()
            .unwrap()
            .write_all(b"GK")
            .unwrap();
        assert!(
            process
                .wait_for_exit(Duration::from_secs(3))
                .unwrap()
                .is_some()
        );
        wait_gone(process.id());
        wait_gone(grandchild);
    }

    #[test]
    fn exit_status_and_spawn_failures_are_observable() {
        let directory = tempfile::tempdir().unwrap();
        let job = JobObject::new().unwrap();
        let process = job.spawn(&shell(directory.path(), "exit 7")).unwrap();
        assert_eq!(
            process.wait_for_exit(Duration::from_secs(3)).unwrap(),
            Some(7),
            "{}",
            fs::read_to_string(directory.path().join("stderr.log")).unwrap()
        );
        assert!(process.wait_for_success(Duration::ZERO).is_err());
        let missing = ProcessCommand::new(
            directory.path().join("missing-runtime"),
            directory.path(),
            directory.path().join("out"),
            directory.path().join("err"),
        );
        assert!(job.spawn(&missing).is_err());
    }

    #[test]
    fn natural_leader_exit_also_reclaims_leftover_descendants() {
        let directory = tempfile::tempdir().unwrap();
        let job = JobObject::new().unwrap();
        let process = job
            .spawn(&shell(
                directory.path(),
                "sleep 60 & echo $! > grandchild; exit 0",
            ))
            .unwrap();
        let grandchild: u32 = wait_file(&directory.path().join("grandchild"))
            .trim()
            .parse()
            .unwrap();
        assert_eq!(
            process.wait_for_exit(Duration::from_secs(3)).unwrap(),
            Some(0)
        );
        wait_gone(grandchild);
    }

    #[test]
    fn parent_subprocess() {
        let Some(directory) = std::env::var_os("NOVWR_TEST_PARENT_DIRECTORY") else {
            return;
        };
        let directory = PathBuf::from(directory);
        let job = JobObject::new().unwrap();
        let process = job
            .spawn(&shell(&directory, "sleep 60 & echo $! > grandchild; wait"))
            .unwrap();
        let guardian = process.state.guardian.lock().unwrap().id();
        let grandchild: u32 = wait_file(&directory.join("grandchild"))
            .trim()
            .parse()
            .unwrap();
        fs::write(
            directory.join("owned-pids.json"),
            serde_json::to_vec(&[guardian, process.id(), grandchild]).unwrap(),
        )
        .unwrap();
        loop {
            thread::sleep(Duration::from_secs(60));
        }
    }

    #[test]
    fn killing_app_parent_reclaims_guardian_backend_and_grandchild() {
        let directory = tempfile::tempdir().unwrap();
        let mut parent = Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "macos::process::tests::parent_subprocess",
                "--nocapture",
            ])
            .env("NOVWR_TEST_PARENT_DIRECTORY", directory.path())
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(open_log(&directory.path().join("parent-error.log")).unwrap())
            .spawn()
            .unwrap();
        let pids = wait_file(&directory.path().join("owned-pids.json"));
        let pids: Vec<u32> = serde_json::from_str(&pids).unwrap();
        parent.kill().unwrap(); // SIGKILL: no Rust Drop or Python callback runs.
        assert_eq!(parent.wait().unwrap().signal(), Some(libc::SIGKILL));
        for pid in pids {
            wait_gone(pid);
        }
    }
}
