use std::collections::BTreeMap;
use std::ffi::{OsStr, OsString};
use std::fs::{File, OpenOptions};
use std::io;
use std::mem::size_of;
use std::os::windows::ffi::OsStrExt;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use windows_sys::Win32::Foundation::{
    HANDLE, HANDLE_FLAG_INHERIT, SetHandleInformation, WAIT_FAILED, WAIT_OBJECT_0, WAIT_TIMEOUT,
};
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
    SetInformationJobObject, TerminateJobObject,
};
use windows_sys::Win32::System::Threading::{
    CREATE_NO_WINDOW, CREATE_SUSPENDED, CREATE_UNICODE_ENVIRONMENT, CreateProcessW,
    GetExitCodeProcess, PROCESS_INFORMATION, ResumeThread, STARTF_USESTDHANDLES, STARTUPINFOW,
    TerminateProcess, WaitForSingleObject,
};

pub const DEFAULT_TERMINATION_EXIT_CODE: u32 = 1;

const MAX_COMMAND_LINE_UNITS: usize = 32_767;
const MAX_BOUNDED_WAIT_MILLISECONDS: u128 = (u32::MAX - 1) as u128;
const FAILED_THREAD_RESUME: u32 = u32::MAX;
const CREATED_PROCESS_CLEANUP_TIMEOUT: Duration = Duration::from_secs(5);

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

    pub fn set_env(mut self, name: impl Into<OsString>, value: impl Into<OsString>) -> Self {
        self.environment.set(name, value);
        self
    }
}

#[derive(Debug)]
pub struct JobObject {
    handle: OwnedHandle,
}

impl JobObject {
    pub fn new() -> io::Result<Self> {
        let raw_handle = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
        if raw_handle.is_null() {
            return Err(last_operation_error("CreateJobObjectW"));
        }
        let handle = unsafe { OwnedHandle::from_raw_handle(raw_handle.cast()) };

        if unsafe { SetHandleInformation(raw_handle, HANDLE_FLAG_INHERIT, 0) } == 0 {
            return Err(last_operation_error(
                "SetHandleInformation(job, non-inheritable)",
            ));
        }

        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if unsafe {
            SetInformationJobObject(
                raw_handle,
                JobObjectExtendedLimitInformation,
                (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        } == 0
        {
            return Err(last_operation_error(
                "SetInformationJobObject(KILL_ON_JOB_CLOSE)",
            ));
        }

        Ok(Self { handle })
    }

    pub fn spawn(&self, command: &ProcessCommand) -> io::Result<ManagedProcess> {
        validate_absolute_path(&command.executable, "runtime executable")?;
        validate_absolute_path(&command.current_directory, "runtime current directory")?;
        validate_absolute_path(&command.stdout_path, "runtime stdout log")?;
        validate_absolute_path(&command.stderr_path, "runtime stderr log")?;

        let application_name =
            encode_nul_terminated(command.executable.as_os_str(), "runtime executable path")?;
        let current_directory = encode_nul_terminated(
            command.current_directory.as_os_str(),
            "runtime current directory",
        )?;
        let mut command_line = build_command_line(&command.executable, &command.arguments)?;
        let environment = build_environment_block(&command.environment)?;

        let stdin = OpenOptions::new().read(true).open("NUL")?;
        let stdout = open_log_file(&command.stdout_path)?;
        let stderr = open_log_file(&command.stderr_path)?;
        let inherited_stdio = InheritedHandleGuard::new([&stdin, &stdout, &stderr])?;

        let startup = STARTUPINFOW {
            cb: size_of::<STARTUPINFOW>() as u32,
            dwFlags: STARTF_USESTDHANDLES,
            hStdInput: file_handle(&stdin),
            hStdOutput: file_handle(&stdout),
            hStdError: file_handle(&stderr),
            ..STARTUPINFOW::default()
        };
        let mut process_information = PROCESS_INFORMATION::default();
        // No child code may run before assignment, otherwise descendants can escape the Job.
        let creation_flags = CREATE_SUSPENDED | CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT;

        let created = unsafe {
            CreateProcessW(
                application_name.as_ptr(),
                command_line.as_mut_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                1,
                creation_flags,
                environment.as_ptr().cast(),
                current_directory.as_ptr(),
                &startup,
                &mut process_information,
            )
        };
        let create_error = (created == 0).then(|| last_operation_error("CreateProcessW"));
        drop(inherited_stdio);
        drop((stdin, stdout, stderr));

        if let Some(error) = create_error {
            return Err(error);
        }
        if process_information.hProcess.is_null() || process_information.hThread.is_null() {
            cleanup_incomplete_process_information(&process_information);
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "CreateProcessW succeeded without valid process and thread handles",
            ));
        }

        let process_handle =
            unsafe { OwnedHandle::from_raw_handle(process_information.hProcess.cast()) };
        let thread_handle =
            unsafe { OwnedHandle::from_raw_handle(process_information.hThread.cast()) };

        if unsafe { AssignProcessToJobObject(self.raw_handle(), raw_handle(&process_handle)) } == 0
        {
            let assign_error = last_operation_error("AssignProcessToJobObject");
            return Err(terminate_after_spawn_failure(&process_handle, assign_error));
        }

        if unsafe { ResumeThread(raw_handle(&thread_handle)) } == FAILED_THREAD_RESUME {
            let resume_error = last_operation_error("ResumeThread");
            return Err(terminate_after_spawn_failure(&process_handle, resume_error));
        }

        drop(thread_handle);
        Ok(ManagedProcess {
            handle: process_handle,
            process_id: process_information.dwProcessId,
        })
    }

    pub fn terminate(&self, exit_code: u32) -> io::Result<()> {
        if unsafe { TerminateJobObject(self.raw_handle(), exit_code) } == 0 {
            return Err(last_operation_error("TerminateJobObject"));
        }
        Ok(())
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
            let remaining = timeout.saturating_sub(started.elapsed());
            if process.wait_for_exit(remaining)?.is_none() {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    format!(
                        "process {} did not exit within {:?} after terminating its Job Object",
                        process.process_id, timeout
                    ),
                ));
            }
        }
        Ok(())
    }

    fn raw_handle(&self) -> HANDLE {
        raw_handle(&self.handle)
    }
}

impl Drop for JobObject {
    fn drop(&mut self) {
        unsafe {
            TerminateJobObject(self.raw_handle(), DEFAULT_TERMINATION_EXIT_CODE);
        }
    }
}

#[derive(Debug)]
#[must_use = "dropping the process handle does not stop the Job Object"]
pub struct ManagedProcess {
    handle: OwnedHandle,
    process_id: u32,
}

impl ManagedProcess {
    pub fn id(&self) -> u32 {
        self.process_id
    }

    pub fn is_running(&self) -> io::Result<bool> {
        match unsafe { WaitForSingleObject(self.raw_handle(), 0) } {
            WAIT_TIMEOUT => Ok(true),
            WAIT_OBJECT_0 => Ok(false),
            WAIT_FAILED => Err(last_operation_error("WaitForSingleObject(liveness)")),
            status => Err(io::Error::other(format!(
                "WaitForSingleObject returned unexpected status {status}"
            ))),
        }
    }

    pub fn exit_code(&self) -> io::Result<Option<u32>> {
        if self.is_running()? {
            return Ok(None);
        }
        self.exit_code_after_signal().map(Some)
    }

    pub fn wait_for_exit(&self, timeout: Duration) -> io::Result<Option<u32>> {
        match unsafe { WaitForSingleObject(self.raw_handle(), duration_millis(timeout)) } {
            WAIT_OBJECT_0 => self.exit_code_after_signal().map(Some),
            WAIT_TIMEOUT => Ok(None),
            WAIT_FAILED => Err(last_operation_error("WaitForSingleObject(exit)")),
            status => Err(io::Error::other(format!(
                "WaitForSingleObject returned unexpected status {status}"
            ))),
        }
    }

    pub fn wait_for_success(&self, timeout: Duration) -> io::Result<()> {
        match self.wait_for_exit(timeout)? {
            Some(0) => Ok(()),
            Some(exit_code) => Err(io::Error::other(format!(
                "process {} exited with code {exit_code}",
                self.process_id
            ))),
            None => Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "process {} did not exit within {:?}",
                    self.process_id, timeout
                ),
            )),
        }
    }

    fn exit_code_after_signal(&self) -> io::Result<u32> {
        let mut exit_code = 0;
        if unsafe { GetExitCodeProcess(self.raw_handle(), &mut exit_code) } == 0 {
            return Err(last_operation_error("GetExitCodeProcess"));
        }
        Ok(exit_code)
    }

    fn raw_handle(&self) -> HANDLE {
        raw_handle(&self.handle)
    }
}

fn validate_absolute_path(path: &Path, label: &str) -> io::Result<()> {
    if path.is_absolute() {
        return Ok(());
    }
    Err(io::Error::new(
        io::ErrorKind::InvalidInput,
        format!("{label} must be an absolute path: {}", path.display()),
    ))
}

fn open_log_file(path: &Path) -> io::Result<File> {
    OpenOptions::new().create(true).append(true).open(path)
}

fn file_handle(file: &File) -> HANDLE {
    file.as_raw_handle().cast()
}

fn raw_handle(handle: &OwnedHandle) -> HANDLE {
    handle.as_raw_handle().cast()
}

fn set_file_inheritable(file: &File) -> io::Result<()> {
    if unsafe { SetHandleInformation(file_handle(file), HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT) }
        == 0
    {
        return Err(last_operation_error(
            "SetHandleInformation(stdio, inheritable)",
        ));
    }
    Ok(())
}

struct InheritedHandleGuard<'a> {
    files: [&'a File; 3],
    marked_inheritable: usize,
}

impl<'a> InheritedHandleGuard<'a> {
    fn new(files: [&'a File; 3]) -> io::Result<Self> {
        let mut guard = Self {
            files,
            marked_inheritable: 0,
        };
        for index in 0..guard.files.len() {
            set_file_inheritable(guard.files[index])?;
            guard.marked_inheritable += 1;
        }
        Ok(guard)
    }
}

impl Drop for InheritedHandleGuard<'_> {
    fn drop(&mut self) {
        for file in self.files.iter().take(self.marked_inheritable) {
            clear_file_inheritance(file);
        }
    }
}

fn clear_file_inheritance(file: &File) {
    unsafe {
        SetHandleInformation(file_handle(file), HANDLE_FLAG_INHERIT, 0);
    }
}

fn cleanup_incomplete_process_information(process_information: &PROCESS_INFORMATION) {
    if !process_information.hProcess.is_null() {
        let process = unsafe { OwnedHandle::from_raw_handle(process_information.hProcess.cast()) };
        let _ = terminate_created_process(&process, DEFAULT_TERMINATION_EXIT_CODE);
    }
    if !process_information.hThread.is_null() {
        drop(unsafe { OwnedHandle::from_raw_handle(process_information.hThread.cast()) });
    }
}

fn terminate_created_process(process: &OwnedHandle, exit_code: u32) -> io::Result<()> {
    if unsafe { TerminateProcess(raw_handle(process), exit_code) } == 0 {
        return Err(last_operation_error("TerminateProcess(cleanup)"));
    }
    match unsafe {
        WaitForSingleObject(
            raw_handle(process),
            duration_millis(CREATED_PROCESS_CLEANUP_TIMEOUT),
        )
    } {
        WAIT_OBJECT_0 => Ok(()),
        WAIT_TIMEOUT => Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "terminated process did not exit during cleanup",
        )),
        WAIT_FAILED => Err(last_operation_error(
            "WaitForSingleObject(created process cleanup)",
        )),
        status => Err(io::Error::other(format!(
            "WaitForSingleObject returned unexpected cleanup status {status}"
        ))),
    }
}

fn terminate_after_spawn_failure(process: &OwnedHandle, operation_error: io::Error) -> io::Error {
    match terminate_created_process(process, DEFAULT_TERMINATION_EXIT_CODE) {
        Ok(()) => operation_error,
        Err(cleanup_error) => io::Error::new(
            cleanup_error.kind(),
            format!(
                "{operation_error}; failed to terminate the incomplete process: {cleanup_error}"
            ),
        ),
    }
}

fn last_operation_error(operation: &str) -> io::Error {
    let source = io::Error::last_os_error();
    io::Error::new(source.kind(), format!("{operation} failed: {source}"))
}

fn duration_millis(duration: Duration) -> u32 {
    let nanos_after_millis = duration.subsec_nanos() % 1_000_000;
    let mut millis = duration.as_millis();
    if nanos_after_millis != 0 {
        millis = millis.saturating_add(1);
    }
    millis.min(MAX_BOUNDED_WAIT_MILLISECONDS) as u32
}

fn encode_nul_terminated(value: &OsStr, label: &str) -> io::Result<Vec<u16>> {
    let mut encoded: Vec<u16> = value.encode_wide().collect();
    if encoded.contains(&0) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("{label} contains an embedded NUL"),
        ));
    }
    encoded.push(0);
    Ok(encoded)
}

fn build_command_line(executable: &Path, arguments: &[OsString]) -> io::Result<Vec<u16>> {
    let mut command_line = quote_windows_argument(executable.as_os_str())?;
    for argument in arguments {
        command_line.push(b' ' as u16);
        command_line.extend(quote_windows_argument(argument)?);
    }
    command_line.push(0);

    if command_line.len() > MAX_COMMAND_LINE_UNITS {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("Windows command line exceeds {MAX_COMMAND_LINE_UNITS} UTF-16 code units"),
        ));
    }
    Ok(command_line)
}

fn quote_windows_argument(argument: &OsStr) -> io::Result<Vec<u16>> {
    let encoded: Vec<u16> = argument.encode_wide().collect();
    if encoded.contains(&0) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "process argument contains an embedded NUL",
        ));
    }

    let requires_quotes = encoded.is_empty()
        || encoded
            .iter()
            .any(|unit| *unit == b' ' as u16 || *unit == b'\t' as u16 || *unit == b'"' as u16);
    if !requires_quotes {
        return Ok(encoded);
    }

    let mut quoted = Vec::with_capacity(encoded.len() + 2);
    quoted.push(b'"' as u16);
    let mut backslash_count = 0usize;

    // Match the Microsoft CRT rules for backslashes immediately before quotes.
    for unit in encoded {
        if unit == b'\\' as u16 {
            backslash_count += 1;
            continue;
        }

        if unit == b'"' as u16 {
            quoted.extend(std::iter::repeat_n(b'\\' as u16, backslash_count * 2 + 1));
            quoted.push(unit);
        } else {
            quoted.extend(std::iter::repeat_n(b'\\' as u16, backslash_count));
            quoted.push(unit);
        }
        backslash_count = 0;
    }

    quoted.extend(std::iter::repeat_n(b'\\' as u16, backslash_count * 2));
    quoted.push(b'"' as u16);
    Ok(quoted)
}

#[derive(Debug)]
struct EnvironmentEntry {
    key: Vec<u16>,
    value: Vec<u16>,
}

fn build_environment_block(delta: &EnvironmentDelta) -> io::Result<Vec<u16>> {
    build_environment_block_from(std::env::vars_os(), delta)
}

fn build_environment_block_from<I>(base: I, delta: &EnvironmentDelta) -> io::Result<Vec<u16>>
where
    I: IntoIterator<Item = (OsString, OsString)>,
{
    let mut entries = BTreeMap::<Vec<u16>, EnvironmentEntry>::new();
    for (key, value) in base {
        insert_environment_entry(&mut entries, &key, &value, false)?;
    }

    for key in &delta.removals {
        validate_explicit_environment_key(key)?;
        entries.remove(&normalized_environment_key(key)?);
    }
    for (key, value) in &delta.additions {
        validate_explicit_environment_key(key)?;
        insert_environment_entry(&mut entries, key, value, true)?;
    }

    let mut block = Vec::new();
    for entry in entries.into_values() {
        block.extend(entry.key);
        block.push(b'=' as u16);
        block.extend(entry.value);
        block.push(0);
    }
    if block.is_empty() {
        block.push(0);
    }
    block.push(0);
    Ok(block)
}

fn insert_environment_entry(
    entries: &mut BTreeMap<Vec<u16>, EnvironmentEntry>,
    key: &OsStr,
    value: &OsStr,
    explicit: bool,
) -> io::Result<()> {
    if explicit {
        validate_explicit_environment_key(key)?;
    }
    let key_units = environment_units(key, "environment variable name")?;
    if key_units.is_empty() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "environment variable name cannot be empty",
        ));
    }
    if !explicit && key_units.iter().skip(1).any(|unit| *unit == b'=' as u16) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "environment variable name contains '='",
        ));
    }
    let value_units = environment_units(value, "environment variable value")?;
    entries.insert(
        normalize_environment_units(&key_units),
        EnvironmentEntry {
            key: key_units,
            value: value_units,
        },
    );
    Ok(())
}

fn validate_explicit_environment_key(key: &OsStr) -> io::Result<()> {
    let units = environment_units(key, "environment variable name")?;
    if units.is_empty() || units.contains(&(b'=' as u16)) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "environment variable name must be non-empty and cannot contain '='",
        ));
    }
    Ok(())
}

fn normalized_environment_key(key: &OsStr) -> io::Result<Vec<u16>> {
    let units = environment_units(key, "environment variable name")?;
    Ok(normalize_environment_units(&units))
}

fn normalize_environment_units(units: &[u16]) -> Vec<u16> {
    units
        .iter()
        .map(|unit| match *unit {
            value if value >= b'a' as u16 && value <= b'z' as u16 => value - 32,
            value => value,
        })
        .collect()
}

fn environment_units(value: &OsStr, label: &str) -> io::Result<Vec<u16>> {
    let units: Vec<u16> = value.encode_wide().collect();
    if units.contains(&0) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("{label} contains an embedded NUL"),
        ));
    }
    Ok(units)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};
    use windows_sys::Win32::Foundation::GetHandleInformation;
    use windows_sys::Win32::System::Threading::{OpenProcess, PROCESS_SYNCHRONIZE};

    const PROCESS_TREE_STARTUP_TIMEOUT: Duration = Duration::from_secs(10);
    const PROCESS_TREE_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(5);

    fn decode_nul_terminated(value: &[u16]) -> String {
        String::from_utf16(&value[..value.len() - 1]).expect("valid test UTF-16")
    }

    fn decode_environment_block(block: &[u16]) -> Vec<String> {
        block[..block.len() - 1]
            .split(|unit| *unit == 0)
            .filter(|entry| !entry.is_empty())
            .map(|entry| String::from_utf16(entry).expect("valid test UTF-16"))
            .collect()
    }

    #[test]
    fn windows_command_line_quotes_empty_spaces_quotes_and_trailing_backslashes() {
        let arguments = vec![
            OsString::from("serve"),
            OsString::from(""),
            OsString::from("two words"),
            OsString::from("quote\"inside"),
            OsString::from("C:\\trailing slash\\"),
        ];

        let command_line = build_command_line(
            Path::new(r"C:\Program Files\NovWr\novwr-runtime.exe"),
            &arguments,
        )
        .expect("command line");

        assert_eq!(
            decode_nul_terminated(&command_line),
            r#""C:\Program Files\NovWr\novwr-runtime.exe" serve "" "two words" "quote\"inside" "C:\trailing slash\\""#
        );
    }

    #[test]
    fn environment_delta_removes_case_insensitively_and_additions_win() {
        let base = vec![
            (OsString::from("Path"), OsString::from("old")),
            (OsString::from("REMOVE_ME"), OsString::from("gone")),
            (OsString::from("Keep"), OsString::from("value")),
        ];
        let mut delta = EnvironmentDelta::new();
        delta.remove("remove_me");
        delta.remove("PATH");
        delta.set("path", "new");
        delta.set("ADD", "added");

        let block = build_environment_block_from(base, &delta).expect("environment block");

        assert_eq!(
            decode_environment_block(&block),
            vec!["ADD=added", "Keep=value", "path=new"]
        );
        assert_eq!(&block[block.len() - 2..], &[0, 0]);
    }

    #[test]
    fn environment_block_rejects_invalid_explicit_names() {
        let delta = EnvironmentDelta::new().with_set("INVALID=NAME", "value");

        let error = build_environment_block_from(Vec::new(), &delta)
            .expect_err("invalid environment key must fail");

        assert_eq!(error.kind(), io::ErrorKind::InvalidInput);
    }

    #[test]
    fn empty_environment_block_has_required_double_nul() {
        let block = build_environment_block_from(Vec::new(), &EnvironmentDelta::new())
            .expect("empty environment block");

        assert_eq!(block, vec![0, 0]);
    }

    #[test]
    fn job_handle_is_non_inheritable() {
        let job = JobObject::new().expect("job object");
        let mut flags = 0;

        assert_ne!(
            unsafe { GetHandleInformation(job.raw_handle(), &mut flags) },
            0
        );
        assert_eq!(flags & HANDLE_FLAG_INHERIT, 0);
    }

    #[test]
    fn terminate_and_wait_stops_managed_process() {
        let test_dir = create_test_directory("terminate");
        let job = JobObject::new().expect("job object");
        let process = job
            .spawn(&long_running_command(&test_dir))
            .expect("managed process");

        assert!(process.is_running().expect("liveness"));
        job.terminate_and_wait(
            &[&process],
            DEFAULT_TERMINATION_EXIT_CODE,
            Duration::from_secs(5),
        )
        .expect("bounded job termination");
        assert!(process.exit_code().expect("exit code").is_some());

        let _ = std::fs::remove_dir_all(test_dir);
    }

    #[test]
    fn dropping_job_stops_managed_process() {
        let test_dir = create_test_directory("drop");
        let process = {
            let job = JobObject::new().expect("job object");
            let process = job
                .spawn(&long_running_command(&test_dir))
                .expect("managed process");
            assert!(process.is_running().expect("liveness"));
            process
        };

        assert!(
            process
                .wait_for_exit(Duration::from_secs(5))
                .expect("wait after job drop")
                .is_some()
        );

        let _ = std::fs::remove_dir_all(test_dir);
    }

    #[test]
    fn terminate_job_stops_system32_grandchild() {
        let test_dir = create_test_directory("terminate-tree");
        let job = JobObject::new().expect("job object");
        let (parent, grandchild, grandchild_id) = spawn_managed_process_tree(&job, &test_dir);

        job.terminate_and_wait(
            &[&parent],
            DEFAULT_TERMINATION_EXIT_CODE,
            PROCESS_TREE_SHUTDOWN_TIMEOUT,
        )
        .expect("bounded process-tree termination");
        assert_process_exited(&grandchild, grandchild_id, PROCESS_TREE_SHUTDOWN_TIMEOUT);

        drop((parent, grandchild, job));
        let _ = std::fs::remove_dir_all(test_dir);
    }

    #[test]
    fn dropping_job_stops_system32_grandchild() {
        let test_dir = create_test_directory("drop-tree");
        let (parent, grandchild, grandchild_id) = {
            let job = JobObject::new().expect("job object");
            spawn_managed_process_tree(&job, &test_dir)
        };

        assert!(
            parent
                .wait_for_exit(PROCESS_TREE_SHUTDOWN_TIMEOUT)
                .expect("wait for managed parent after Job drop")
                .is_some(),
            "managed parent {} survived Job drop",
            parent.id()
        );
        assert_process_exited(&grandchild, grandchild_id, PROCESS_TREE_SHUTDOWN_TIMEOUT);

        drop((parent, grandchild));
        let _ = std::fs::remove_dir_all(test_dir);
    }

    fn spawn_managed_process_tree(
        job: &JobObject,
        test_dir: &Path,
    ) -> (ManagedProcess, OwnedHandle, u32) {
        let pid_path = test_dir.join("grandchild.pid");
        let parent = job
            .spawn(&powershell_process_tree_command(test_dir, &pid_path))
            .expect("managed PowerShell parent");
        let grandchild_id = wait_for_process_id(&pid_path, PROCESS_TREE_STARTUP_TIMEOUT);
        let grandchild = open_process_for_wait(grandchild_id).expect("open System32 grandchild");

        assert!(parent.is_running().expect("managed parent liveness"));
        assert_process_running(&grandchild, grandchild_id);
        (parent, grandchild, grandchild_id)
    }

    fn powershell_process_tree_command(test_dir: &Path, pid_path: &Path) -> ProcessCommand {
        let system_root = std::env::var_os("SystemRoot").expect("SystemRoot");
        let powershell = PathBuf::from(system_root)
            .join("System32")
            .join("WindowsPowerShell")
            .join("v1.0")
            .join("powershell.exe");
        let script = concat!(
            "$child = Start-Process ",
            "-FilePath (Join-Path $env:SystemRoot 'System32\\PING.EXE') ",
            "-ArgumentList @('-t', '127.0.0.1') ",
            "-WindowStyle Hidden -PassThru; ",
            "[System.IO.File]::WriteAllText(",
            "$env:NOVWR_JOB_TEST_GRANDCHILD_PID, [string]$child.Id); ",
            "Wait-Process -Id $child.Id"
        );

        ProcessCommand::new(
            powershell,
            test_dir,
            test_dir.join("parent.stdout.log"),
            test_dir.join("parent.stderr.log"),
        )
        .arg("-NoLogo")
        .arg("-NoProfile")
        .arg("-NonInteractive")
        .arg("-Command")
        .arg(script)
        .set_env("NOVWR_JOB_TEST_GRANDCHILD_PID", pid_path.as_os_str())
    }

    fn wait_for_process_id(path: &Path, timeout: Duration) -> u32 {
        let deadline = Instant::now() + timeout;
        loop {
            match std::fs::read_to_string(path) {
                Ok(value) if value.trim().is_empty() => {}
                Ok(value) => {
                    return value
                        .trim()
                        .parse::<u32>()
                        .expect("grandchild PID file must contain a process ID");
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                Err(error) => panic!("read grandchild PID file {}: {error}", path.display()),
            }

            assert!(
                Instant::now() < deadline,
                "PowerShell did not publish the grandchild PID at {} within {:?}",
                path.display(),
                timeout
            );
            std::thread::sleep(Duration::from_millis(50));
        }
    }

    fn open_process_for_wait(process_id: u32) -> io::Result<OwnedHandle> {
        let handle = unsafe { OpenProcess(PROCESS_SYNCHRONIZE, 0, process_id) };
        if handle.is_null() {
            return Err(last_operation_error("OpenProcess(grandchild)"));
        }
        Ok(unsafe { OwnedHandle::from_raw_handle(handle.cast()) })
    }

    fn assert_process_running(process: &OwnedHandle, process_id: u32) {
        match unsafe { WaitForSingleObject(raw_handle(process), 0) } {
            WAIT_TIMEOUT => {}
            WAIT_OBJECT_0 => panic!("process {process_id} exited before Job termination"),
            WAIT_FAILED => panic!(
                "inspect process {process_id} before Job termination: {}",
                last_operation_error("WaitForSingleObject(grandchild liveness)")
            ),
            status => panic!(
                "WaitForSingleObject returned unexpected status {status} for process {process_id}"
            ),
        }
    }

    fn assert_process_exited(process: &OwnedHandle, process_id: u32, timeout: Duration) {
        match unsafe { WaitForSingleObject(raw_handle(process), duration_millis(timeout)) } {
            WAIT_OBJECT_0 => {}
            WAIT_TIMEOUT => {
                panic!("process {process_id} survived Job termination for {timeout:?}")
            }
            WAIT_FAILED => panic!(
                "wait for process {process_id} after Job termination: {}",
                last_operation_error("WaitForSingleObject(grandchild exit)")
            ),
            status => panic!(
                "WaitForSingleObject returned unexpected status {status} for process {process_id}"
            ),
        }
    }

    fn long_running_command(test_dir: &Path) -> ProcessCommand {
        let system_root = std::env::var_os("SystemRoot").expect("SystemRoot");
        let ping = PathBuf::from(system_root).join("System32").join("PING.EXE");
        ProcessCommand::new(
            ping,
            test_dir,
            test_dir.join("stdout.log"),
            test_dir.join("stderr.log"),
        )
        .arg("-t")
        .arg("127.0.0.1")
    }

    fn create_test_directory(label: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "novwr-job-object-{label}-{}-{nonce}",
            std::process::id()
        ));
        std::fs::create_dir_all(&path).expect("test directory");
        path
    }
}
