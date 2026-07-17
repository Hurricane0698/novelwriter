use std::io;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::thread;
use std::time::{Duration, Instant};

use reqwest::blocking::Client;
use reqwest::redirect::Policy;
use serde::Deserialize;
use thiserror::Error;
use tracing::{info, warn};

use crate::paths::AppPaths;
use crate::windows::{
    DEFAULT_TERMINATION_EXIT_CODE, EnvironmentDelta, JobObject, ManagedProcess, ProcessCommand,
    ShutdownEvent,
};

pub const APP_URL: &str = "http://127.0.0.1:8000/";
pub const HEALTH_URL: &str = "http://127.0.0.1:8000/api/health";
const LOCAL_BIND_ADDRESS: &str = "127.0.0.1:8000";

const BOOTSTRAP_TIMEOUT: Duration = Duration::from_secs(120);
const HEALTH_TIMEOUT: Duration = Duration::from_secs(45);
const HEALTH_RETRY_INTERVAL: Duration = Duration::from_secs(1);
const HTTP_REQUEST_TIMEOUT: Duration = Duration::from_secs(3);
const WORKER_STARTUP_GRACE: Duration = Duration::from_secs(1);
const SERVER_GRACEFUL_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(10);
const PERSISTENT_JOB_STALE_TIMEOUT_SECONDS: u64 = 900;
const WORKER_GRACEFUL_SHUTDOWN_TIMEOUT: Duration =
    Duration::from_secs(PERSISTENT_JOB_STALE_TIMEOUT_SECONDS);
const FORCED_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(5);
const PROCESS_MONITOR_INTERVAL: Duration = Duration::from_secs(1);
const STATIC_ROOT_MARKER: &str = "<div id=\"root\">";
const SHUTDOWN_EVENT_ENVIRONMENT_KEY: &str = "NOVWR_DESKTOP_SHUTDOWN_EVENT";

const MODEL_CREDENTIAL_ENVIRONMENT_KEYS: [&str; 6] = [
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "HOSTED_LLM_API_KEY",
    "HOSTED_LLM_BASE_URL",
    "HOSTED_LLM_MODEL",
];

#[derive(Debug, Error)]
pub enum RuntimeError {
    #[error("desktop runtime path is invalid: {0}")]
    InvalidRuntimePath(String),
    #[error("create desktop Job Object: {0}")]
    CreateJob(#[source] io::Error),
    #[error("create desktop shutdown event: {0}")]
    CreateShutdownEvent(#[source] io::Error),
    #[error("fixed desktop port {LOCAL_BIND_ADDRESS} is unavailable: {0}")]
    PortUnavailable(#[source] io::Error),
    #[error("start database bootstrap: {0}")]
    StartBootstrap(#[source] io::Error),
    #[error("database bootstrap failed: {0}")]
    Bootstrap(#[source] io::Error),
    #[error("start local server: {0}")]
    StartServer(#[source] io::Error),
    #[error("local server exited during startup with code {exit_code}")]
    ServerExitedDuringStartup { exit_code: u32 },
    #[error("local server did not become ready: {last_error}")]
    HealthTimeout { last_error: String },
    #[error("local SPA static entry is unavailable: {0}")]
    StaticEntry(String),
    #[error("start background worker: {0}")]
    StartWorker(#[source] io::Error),
    #[error("background worker exited during startup with code {exit_code}")]
    WorkerExitedDuringStartup { exit_code: u32 },
    #[error("local server exited unexpectedly with code {exit_code}")]
    ServerExited { exit_code: u32 },
    #[error("background worker exited unexpectedly with code {exit_code}")]
    WorkerExited { exit_code: u32 },
    #[error("inspect desktop runtime process: {0}")]
    InspectProcess(#[source] io::Error),
    #[error("shut down desktop runtime processes: {0}")]
    Shutdown(#[source] io::Error),
}

impl RuntimeError {
    pub fn user_summary(&self) -> &'static str {
        match self {
            Self::InvalidRuntimePath(_) => "桌面运行时文件缺失或损坏。",
            Self::CreateJob(_) | Self::CreateShutdownEvent(_) => "无法建立本地进程监管。",
            Self::PortUnavailable(_) => "本地端口 8000 已被占用。",
            Self::StartBootstrap(_) | Self::Bootstrap(_) => "本地数据库初始化失败。",
            Self::StartServer(_)
            | Self::ServerExitedDuringStartup { .. }
            | Self::HealthTimeout { .. }
            | Self::StaticEntry(_) => "本地服务启动失败。",
            Self::StartWorker(_) | Self::WorkerExitedDuringStartup { .. } => {
                "后台任务进程启动失败。"
            }
            Self::ServerExited { .. } => "本地服务意外退出。",
            Self::WorkerExited { .. } => "后台任务进程意外退出。",
            Self::InspectProcess(_) | Self::Shutdown(_) => "本地进程监管失败。",
        }
    }
}

pub struct RuntimeSupervisor {
    job: JobObject,
    shutdown_event: ShutdownEvent,
    server: ManagedProcess,
    worker: ManagedProcess,
    terminated: bool,
}

impl RuntimeSupervisor {
    pub fn start(
        runtime_directory: &Path,
        paths: &AppPaths,
        jwt_secret: &str,
    ) -> Result<Self, RuntimeError> {
        let executable = runtime_directory.join("novwr-runtime.exe");
        if !runtime_directory.is_absolute() || !runtime_directory.is_dir() {
            return Err(RuntimeError::InvalidRuntimePath(
                runtime_directory.display().to_string(),
            ));
        }
        if !executable.is_file() {
            return Err(RuntimeError::InvalidRuntimePath(
                executable.display().to_string(),
            ));
        }
        require_available_port()?;

        let job = JobObject::new().map_err(RuntimeError::CreateJob)?;
        let shutdown_event = ShutdownEvent::create().map_err(RuntimeError::CreateShutdownEvent)?;
        let client = Client::builder()
            .no_proxy()
            .redirect(Policy::none())
            .timeout(HTTP_REQUEST_TIMEOUT)
            .build()
            .map_err(|error| RuntimeError::HealthTimeout {
                last_error: error.to_string(),
            })?;
        let mut startup = WindowsRuntimeStartup {
            job,
            shutdown_event,
            executable,
            runtime_directory: runtime_directory.to_path_buf(),
            paths,
            jwt_secret,
            client,
            server: None,
            worker: None,
        };
        execute_startup(&mut startup)?;
        startup.finish()
    }

    pub fn check_running(&self) -> Result<(), RuntimeError> {
        if !self
            .server
            .is_running()
            .map_err(RuntimeError::InspectProcess)?
        {
            return Err(RuntimeError::ServerExited {
                exit_code: self
                    .server
                    .exit_code()
                    .map_err(RuntimeError::InspectProcess)?
                    .unwrap_or(u32::MAX),
            });
        }
        if !self
            .worker
            .is_running()
            .map_err(RuntimeError::InspectProcess)?
        {
            return Err(RuntimeError::WorkerExited {
                exit_code: self
                    .worker
                    .exit_code()
                    .map_err(RuntimeError::InspectProcess)?
                    .unwrap_or(u32::MAX),
            });
        }
        Ok(())
    }

    pub fn shutdown(&mut self) -> Result<(), RuntimeError> {
        if self.terminated {
            return Ok(());
        }

        let processes = [&self.server, &self.worker];
        let graceful_result = self
            .shutdown_event
            .signal()
            .and_then(|()| wait_for_graceful_shutdown(&self.server, &self.worker));

        match graceful_shutdown_disposition(&graceful_result) {
            ShutdownDisposition::Complete => {
                info!("desktop runtime processes shut down gracefully");
            }
            ShutdownDisposition::Escalate => {
                match &graceful_result {
                    Ok(GracefulShutdownOutcome::ServerTimedOut) => warn!(
                        timeout_seconds = SERVER_GRACEFUL_SHUTDOWN_TIMEOUT.as_secs(),
                        "desktop server graceful shutdown timed out; terminating Job Object"
                    ),
                    Ok(GracefulShutdownOutcome::WorkerTimedOut) => warn!(
                        timeout_seconds = WORKER_GRACEFUL_SHUTDOWN_TIMEOUT.as_secs(),
                        "desktop worker did not finish its current job; terminating Job Object"
                    ),
                    Err(error) => warn!(
                        error = %error,
                        "desktop runtime graceful shutdown failed; terminating Job Object"
                    ),
                    Ok(GracefulShutdownOutcome::Complete) => {
                        unreachable!("complete graceful shutdown cannot require escalation")
                    }
                }
                self.job
                    .terminate_and_wait(
                        &processes,
                        DEFAULT_TERMINATION_EXIT_CODE,
                        FORCED_SHUTDOWN_TIMEOUT,
                    )
                    .map_err(RuntimeError::Shutdown)?;
            }
        }
        self.terminated = true;
        Ok(())
    }

    pub fn process_ids(&self) -> (u32, u32) {
        (self.server.id(), self.worker.id())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ShutdownDisposition {
    Complete,
    Escalate,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum GracefulShutdownOutcome {
    Complete,
    ServerTimedOut,
    WorkerTimedOut,
}

fn graceful_shutdown_disposition(
    result: &io::Result<GracefulShutdownOutcome>,
) -> ShutdownDisposition {
    match result {
        Ok(GracefulShutdownOutcome::Complete) => ShutdownDisposition::Complete,
        Ok(GracefulShutdownOutcome::ServerTimedOut | GracefulShutdownOutcome::WorkerTimedOut)
        | Err(_) => ShutdownDisposition::Escalate,
    }
}

fn wait_for_graceful_shutdown(
    server: &ManagedProcess,
    worker: &ManagedProcess,
) -> io::Result<GracefulShutdownOutcome> {
    let started = Instant::now();
    if server
        .wait_for_exit(SERVER_GRACEFUL_SHUTDOWN_TIMEOUT)?
        .is_none()
    {
        return Ok(GracefulShutdownOutcome::ServerTimedOut);
    }

    let worker_remaining = WORKER_GRACEFUL_SHUTDOWN_TIMEOUT.saturating_sub(started.elapsed());
    if worker.wait_for_exit(worker_remaining)?.is_none() {
        return Ok(GracefulShutdownOutcome::WorkerTimedOut);
    }
    Ok(GracefulShutdownOutcome::Complete)
}

fn require_available_port() -> Result<(), RuntimeError> {
    let listener = TcpListener::bind(LOCAL_BIND_ADDRESS).map_err(RuntimeError::PortUnavailable)?;
    drop(listener);
    Ok(())
}

pub fn monitor_interval() -> Duration {
    PROCESS_MONITOR_INTERVAL
}

trait StartupOperations {
    fn bootstrap(&mut self) -> Result<(), RuntimeError>;
    fn start_server(&mut self) -> Result<(), RuntimeError>;
    fn wait_for_readiness(&mut self) -> Result<(), RuntimeError>;
    fn start_worker(&mut self) -> Result<(), RuntimeError>;
    fn verify_worker(&mut self) -> Result<(), RuntimeError>;
}

fn execute_startup(operations: &mut impl StartupOperations) -> Result<(), RuntimeError> {
    operations.bootstrap()?;
    operations.start_server()?;
    operations.wait_for_readiness()?;
    operations.start_worker()?;
    operations.verify_worker()?;
    Ok(())
}

struct WindowsRuntimeStartup<'a> {
    job: JobObject,
    shutdown_event: ShutdownEvent,
    executable: PathBuf,
    runtime_directory: PathBuf,
    paths: &'a AppPaths,
    jwt_secret: &'a str,
    client: Client,
    server: Option<ManagedProcess>,
    worker: Option<ManagedProcess>,
}

impl WindowsRuntimeStartup<'_> {
    fn command(&self, command: &'static str, log_prefix: &'static str) -> ProcessCommand {
        ProcessCommand::new(
            &self.executable,
            &self.runtime_directory,
            self.paths.logs.join(format!("{log_prefix}.stdout.log")),
            self.paths.logs.join(format!("{log_prefix}.stderr.log")),
        )
        .arg(command)
        .environment(runtime_environment(self.paths, self.jwt_secret))
    }

    fn supervised_command(
        &self,
        command: &'static str,
        log_prefix: &'static str,
    ) -> ProcessCommand {
        self.command(command, log_prefix)
            .set_env(SHUTDOWN_EVENT_ENVIRONMENT_KEY, self.shutdown_event.name())
    }

    fn finish(mut self) -> Result<RuntimeSupervisor, RuntimeError> {
        let server = self.server.take().ok_or_else(|| {
            RuntimeError::InvalidRuntimePath("server process was not initialized".to_string())
        })?;
        let worker = self.worker.take().ok_or_else(|| {
            RuntimeError::InvalidRuntimePath("worker process was not initialized".to_string())
        })?;
        Ok(RuntimeSupervisor {
            job: self.job,
            shutdown_event: self.shutdown_event,
            server,
            worker,
            terminated: false,
        })
    }
}

impl StartupOperations for WindowsRuntimeStartup<'_> {
    fn bootstrap(&mut self) -> Result<(), RuntimeError> {
        info!("running desktop database bootstrap");
        let process = self
            .job
            .spawn(&self.command("bootstrap", "bootstrap"))
            .map_err(RuntimeError::StartBootstrap)?;
        process
            .wait_for_success(BOOTSTRAP_TIMEOUT)
            .map_err(RuntimeError::Bootstrap)
    }

    fn start_server(&mut self) -> Result<(), RuntimeError> {
        info!("starting desktop local server");
        let process = self
            .job
            .spawn(&self.supervised_command("serve", "server"))
            .map_err(RuntimeError::StartServer)?;
        self.server = Some(process);
        Ok(())
    }

    fn wait_for_readiness(&mut self) -> Result<(), RuntimeError> {
        let server = self.server.as_ref().ok_or_else(|| {
            RuntimeError::InvalidRuntimePath("server process was not initialized".to_string())
        })?;
        let deadline = Instant::now() + HEALTH_TIMEOUT;
        let mut last_error = "health endpoint did not respond".to_string();

        while Instant::now() < deadline {
            if !server.is_running().map_err(RuntimeError::InspectProcess)? {
                return Err(RuntimeError::ServerExitedDuringStartup {
                    exit_code: server
                        .exit_code()
                        .map_err(RuntimeError::InspectProcess)?
                        .unwrap_or(u32::MAX),
                });
            }

            match probe_health(&self.client) {
                Ok(()) => {
                    verify_static_entry(&self.client)?;
                    info!("desktop local server is ready");
                    return Ok(());
                }
                Err(error) => last_error = error,
            }
            thread::sleep(HEALTH_RETRY_INTERVAL);
        }
        Err(RuntimeError::HealthTimeout { last_error })
    }

    fn start_worker(&mut self) -> Result<(), RuntimeError> {
        info!("starting desktop background worker");
        let process = self
            .job
            .spawn(&self.supervised_command("worker", "worker"))
            .map_err(RuntimeError::StartWorker)?;
        self.worker = Some(process);
        Ok(())
    }

    fn verify_worker(&mut self) -> Result<(), RuntimeError> {
        thread::sleep(WORKER_STARTUP_GRACE);
        let worker = self.worker.as_ref().ok_or_else(|| {
            RuntimeError::InvalidRuntimePath("worker process was not initialized".to_string())
        })?;
        if !worker.is_running().map_err(RuntimeError::InspectProcess)? {
            return Err(RuntimeError::WorkerExitedDuringStartup {
                exit_code: worker
                    .exit_code()
                    .map_err(RuntimeError::InspectProcess)?
                    .unwrap_or(u32::MAX),
            });
        }
        Ok(())
    }
}

fn runtime_environment(paths: &AppPaths, jwt_secret: &str) -> EnvironmentDelta {
    let mut environment = EnvironmentDelta::new()
        .with_set("NOVWR_DESKTOP_DATA_DIR", paths.data.as_os_str())
        .with_set("NOVWR_DESKTOP_JWT_SECRET", jwt_secret)
        .with_set(
            "BOOTSTRAP_STALE_JOB_TIMEOUT_SECONDS",
            PERSISTENT_JOB_STALE_TIMEOUT_SECONDS.to_string(),
        )
        .with_set(
            "DERIVED_ASSET_JOB_STALE_TIMEOUT_SECONDS",
            PERSISTENT_JOB_STALE_TIMEOUT_SECONDS.to_string(),
        )
        .with_set(
            "INGEST_JOB_STALE_TIMEOUT_SECONDS",
            PERSISTENT_JOB_STALE_TIMEOUT_SECONDS.to_string(),
        );
    for name in MODEL_CREDENTIAL_ENVIRONMENT_KEYS {
        environment.remove(name);
    }
    environment
}

#[derive(Deserialize)]
struct HealthPayload {
    status: String,
}

fn probe_health(client: &Client) -> Result<(), String> {
    let response = client
        .get(HEALTH_URL)
        .send()
        .and_then(reqwest::blocking::Response::error_for_status)
        .map_err(|error| error.to_string())?;
    let payload = response
        .json::<HealthPayload>()
        .map_err(|error| error.to_string())?;
    if payload.status != "healthy" {
        return Err(format!(
            "health endpoint returned status {:?}",
            payload.status
        ));
    }
    Ok(())
}

fn verify_static_entry(client: &Client) -> Result<(), RuntimeError> {
    let response = client
        .get(APP_URL)
        .send()
        .and_then(reqwest::blocking::Response::error_for_status)
        .map_err(|error| RuntimeError::StaticEntry(error.to_string()))?;
    let body = response
        .text()
        .map_err(|error| RuntimeError::StaticEntry(error.to_string()))?;
    if !body.contains(STATIC_ROOT_MARKER) {
        return Err(RuntimeError::StaticEntry(
            "root document does not contain the SPA mount point".to_string(),
        ));
    }
    Ok(())
}

impl Drop for RuntimeSupervisor {
    fn drop(&mut self) {
        if let Err(error) = self.shutdown() {
            warn!(error = %error, "desktop runtime shutdown during drop failed");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Clone, Copy, Debug, Eq, PartialEq)]
    enum Step {
        Bootstrap,
        Server,
        Health,
        Worker,
        VerifyWorker,
    }

    #[derive(Default)]
    struct FakeStartup {
        events: Vec<Step>,
        fail_at: Option<Step>,
    }

    impl FakeStartup {
        fn record(&mut self, step: Step) -> Result<(), RuntimeError> {
            self.events.push(step);
            if self.fail_at == Some(step) {
                return Err(RuntimeError::InvalidRuntimePath(format!(
                    "injected failure at {step:?}"
                )));
            }
            Ok(())
        }
    }

    impl StartupOperations for FakeStartup {
        fn bootstrap(&mut self) -> Result<(), RuntimeError> {
            self.record(Step::Bootstrap)
        }

        fn start_server(&mut self) -> Result<(), RuntimeError> {
            self.record(Step::Server)
        }

        fn wait_for_readiness(&mut self) -> Result<(), RuntimeError> {
            self.record(Step::Health)
        }

        fn start_worker(&mut self) -> Result<(), RuntimeError> {
            self.record(Step::Worker)
        }

        fn verify_worker(&mut self) -> Result<(), RuntimeError> {
            self.record(Step::VerifyWorker)
        }
    }

    #[test]
    fn startup_order_is_bootstrap_server_health_worker_verification() {
        let mut startup = FakeStartup::default();

        execute_startup(&mut startup).expect("startup must succeed");

        assert_eq!(
            startup.events,
            vec![
                Step::Bootstrap,
                Step::Server,
                Step::Health,
                Step::Worker,
                Step::VerifyWorker,
            ]
        );
    }

    #[test]
    fn startup_stops_immediately_at_each_failed_stage() {
        let sequence = [
            Step::Bootstrap,
            Step::Server,
            Step::Health,
            Step::Worker,
            Step::VerifyWorker,
        ];

        for (index, step) in sequence.into_iter().enumerate() {
            let mut startup = FakeStartup {
                events: Vec::new(),
                fail_at: Some(step),
            };

            assert!(execute_startup(&mut startup).is_err());
            assert_eq!(startup.events, sequence[..=index]);
        }
    }

    #[test]
    fn desktop_urls_and_model_credential_boundary_are_fixed() {
        assert_eq!(APP_URL, "http://127.0.0.1:8000/");
        assert_eq!(HEALTH_URL, "http://127.0.0.1:8000/api/health");
        assert_eq!(LOCAL_BIND_ADDRESS, "127.0.0.1:8000");
        assert_eq!(
            MODEL_CREDENTIAL_ENVIRONMENT_KEYS,
            [
                "OPENAI_API_KEY",
                "OPENAI_BASE_URL",
                "OPENAI_MODEL",
                "HOSTED_LLM_API_KEY",
                "HOSTED_LLM_BASE_URL",
                "HOSTED_LLM_MODEL",
            ]
        );
    }

    #[test]
    fn occupied_fixed_port_fails_before_runtime_startup() {
        let listener = TcpListener::bind(LOCAL_BIND_ADDRESS)
            .expect("the fixed desktop port must be free before this test");

        let error = require_available_port().expect_err("an occupied fixed port must fail");

        assert!(matches!(error, RuntimeError::PortUnavailable(_)));
        drop(listener);
    }

    #[test]
    fn graceful_completion_does_not_escalate() {
        assert_eq!(
            graceful_shutdown_disposition(&Ok(GracefulShutdownOutcome::Complete)),
            ShutdownDisposition::Complete
        );
    }

    #[test]
    fn server_and_worker_timeouts_escalate() {
        assert_eq!(
            graceful_shutdown_disposition(&Ok(GracefulShutdownOutcome::ServerTimedOut)),
            ShutdownDisposition::Escalate
        );
        assert_eq!(
            graceful_shutdown_disposition(&Ok(GracefulShutdownOutcome::WorkerTimedOut)),
            ShutdownDisposition::Escalate
        );
    }

    #[test]
    fn graceful_shutdown_errors_escalate() {
        assert_eq!(
            graceful_shutdown_disposition(&Err(io::Error::other("wait failed"))),
            ShutdownDisposition::Escalate
        );
    }

    #[test]
    fn worker_shutdown_budget_covers_the_persistent_job_stale_window() {
        assert_eq!(SERVER_GRACEFUL_SHUTDOWN_TIMEOUT, Duration::from_secs(10));
        assert_eq!(PERSISTENT_JOB_STALE_TIMEOUT_SECONDS, 900);
        assert_eq!(WORKER_GRACEFUL_SHUTDOWN_TIMEOUT, Duration::from_secs(900));
        assert!(WORKER_GRACEFUL_SHUTDOWN_TIMEOUT > SERVER_GRACEFUL_SHUTDOWN_TIMEOUT);
    }
}
