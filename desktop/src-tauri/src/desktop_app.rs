use std::io;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;

use anyhow::{Context, Result as AnyResult};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{TrayIcon, TrayIconBuilder};
use tauri::webview::PageLoadPayload;
use tauri::{App, AppHandle, Manager, RunEvent, Url, WebviewWindow, WindowEvent};
use tracing::{error, info, warn};

use crate::logging::{self, DesktopLogGuard};
use crate::paths::AppPaths;
use crate::platform;
use crate::runtime::{self, APP_URL, RuntimeSupervisor};
use crate::secret;
use crate::windows::open_directory;
use crate::windows::single_instance::{Acquisition, acquire};

const MAIN_WINDOW_LABEL: &str = "main";
const TRAY_OPEN_ID: &str = "open";
const TRAY_DATA_ID: &str = "open-data";
const TRAY_LOGS_ID: &str = "open-logs";
const TRAY_QUIT_ID: &str = "quit";

struct DesktopState {
    paths: AppPaths,
    // `WebviewWindow::url()` is still `about:blank` during `setup`. Capture the
    // bundled shell URL from the page-load hook instead so failure navigation
    // can never turn `about:blank` into an inert white page.
    local_shell_url: Mutex<Option<Url>>,
    supervisor: Mutex<Option<RuntimeSupervisor>>,
    tray: Mutex<Option<TrayIcon>>,
    log_guard: Mutex<Option<DesktopLogGuard>>,
    exit_requested: AtomicBool,
    // Startup failures are stored here so the local shell page can pull them via
    // the `startup_status` command; navigation with a `?failure=` query alone can
    // race a webview that has not finished loading yet and end up blank.
    startup_failure: Mutex<Option<&'static str>>,
}

impl DesktopState {
    fn new(paths: AppPaths) -> Self {
        Self {
            paths,
            local_shell_url: Mutex::new(None),
            supervisor: Mutex::new(None),
            tray: Mutex::new(None),
            log_guard: Mutex::new(None),
            exit_requested: AtomicBool::new(false),
            startup_failure: Mutex::new(None),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum CloseDisposition {
    Hide,
    Exit,
}

fn close_disposition(exit_requested: bool) -> CloseDisposition {
    if exit_requested {
        CloseDisposition::Exit
    } else {
        CloseDisposition::Hide
    }
}

pub fn run() {
    let context = tauri::generate_context!();
    let mut primary = match acquire(&context.config().identifier)
        .expect("acquire NovWr desktop single-instance gate")
    {
        Acquisition::Primary(primary) => primary,
        Acquisition::Secondary => return,
    };

    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![open_logs, quit, startup_status])
        .on_page_load(handle_page_load)
        .setup(|app| setup(app).map_err(Into::into))
        .build(context)
        .expect("build NovWr desktop application");

    let activation_app = app.handle().clone();
    let activation_listener = primary
        .start_listener(move || {
            let target_app = activation_app.clone();
            activation_app
                .run_on_main_thread(move || show_main_window(&target_app))
                .map_err(|error| {
                    io::Error::other(format!(
                        "schedule duplicate-launch activation on main thread: {error}"
                    ))
                })
        })
        .expect("start NovWr duplicate-launch activation listener");

    app.run(handle_run_event);

    activation_listener
        .shutdown()
        .expect("stop NovWr duplicate-launch activation listener");
    primary
        .release()
        .expect("release NovWr desktop single-instance mutex");
}

fn setup(app: &mut App) -> AnyResult<()> {
    app.get_webview_window(MAIN_WINDOW_LABEL)
        .context("configured main window is missing")?;
    let local_data_root = app
        .path()
        .local_data_dir()
        .context("resolve Windows LocalAppData")?;
    let paths = AppPaths::from_local_data_root(local_data_root);
    app.manage(DesktopState::new(paths));

    let tray = build_tray(app).context("create NovWr tray icon")?;
    *app.state::<DesktopState>()
        .tray
        .lock()
        .expect("desktop tray mutex poisoned") = Some(tray);

    let handle = app.handle().clone();
    thread::spawn(move || start_runtime(handle));
    Ok(())
}

fn handle_page_load(webview: &tauri::Webview, payload: &PageLoadPayload<'_>) {
    if webview.label() != MAIN_WINDOW_LABEL {
        return;
    }
    // Record both Started and Finished events. A very fast runtime can navigate
    // away before the shell's Finished event, but Started already carries the
    // real Tauri URL and is enough to establish the trusted fallback origin.
    let Some(local_shell_url) = normalized_local_shell_url(payload.url()) else {
        return;
    };
    let Some(state) = webview.try_state::<DesktopState>() else {
        return;
    };
    *state
        .local_shell_url
        .lock()
        .expect("desktop local shell URL mutex poisoned") = Some(local_shell_url);
}

fn normalized_local_shell_url(url: &Url) -> Option<Url> {
    let is_local_shell = matches!(
        (url.scheme(), url.host_str()),
        ("http" | "https", Some("tauri.localhost")) | ("tauri", Some("localhost"))
    );
    if !is_local_shell {
        return None;
    }

    let mut normalized = url.clone();
    normalized.set_query(None);
    normalized.set_fragment(None);
    Some(normalized)
}

fn build_tray(app: &App) -> tauri::Result<TrayIcon> {
    let open = MenuItem::with_id(app, TRAY_OPEN_ID, "打开 NovWr", true, None::<&str>)?;
    let data = MenuItem::with_id(app, TRAY_DATA_ID, "打开数据目录", true, None::<&str>)?;
    let logs = MenuItem::with_id(app, TRAY_LOGS_ID, "打开日志", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, TRAY_QUIT_ID, "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &data, &logs, &quit])?;
    let icon = app
        .default_window_icon()
        .cloned()
        .expect("configured default window icon is missing");

    TrayIconBuilder::with_id("novwr")
        .icon(icon)
        .tooltip("NovWr")
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(handle_tray_menu)
        .build(app)
}

fn handle_tray_menu(app: &AppHandle, event: tauri::menu::MenuEvent) {
    match event.id().as_ref() {
        TRAY_OPEN_ID => show_main_window(app),
        TRAY_DATA_ID => open_owned_directory(app, DirectoryKind::Data),
        TRAY_LOGS_ID => open_owned_directory(app, DirectoryKind::Logs),
        TRAY_QUIT_ID => request_exit(app),
        _ => {}
    }
}

fn start_runtime(app: AppHandle) {
    if let Err(error) = start_runtime_inner(&app) {
        error!(error = %error, error_debug = ?error, "desktop startup failed");
        show_failure_window(&app, error.user_summary());
    }
}

fn start_runtime_inner(app: &AppHandle) -> Result<(), StartupError> {
    let state = app.state::<DesktopState>();
    state
        .paths
        .create_directories()
        .map_err(StartupError::CreateDirectories)?;

    let log_guard = logging::initialize(&state.paths.logs).map_err(StartupError::Logging)?;
    *state
        .log_guard
        .lock()
        .expect("desktop logging mutex poisoned") = Some(log_guard);
    info!("starting NovWr desktop shell");

    // Logging is initialized first so unsupported platforms still leave a trace.
    platform::require_supported_windows_x64().map_err(StartupError::Platform)?;

    let jwt_secret = secret::load_or_create_secret(&state.paths.secret)
        .map_err(StartupError::PersistentSecret)?;
    let runtime_directory = app
        .path()
        .resource_dir()
        .map_err(StartupError::ResourceDirectory)?
        .join("runtime");
    let supervisor = RuntimeSupervisor::start(&runtime_directory, &state.paths, &jwt_secret)
        .map_err(StartupError::Runtime)?;
    let process_ids = supervisor.process_ids();
    if let Err(mut supervisor) =
        install_supervisor(&state.exit_requested, &state.supervisor, supervisor)
    {
        if let Err(error) = supervisor.shutdown() {
            warn!(error = %error, "desktop runtime shutdown after exit request failed");
        }
        return Ok(());
    }
    info!(
        server_pid = process_ids.0,
        worker_pid = process_ids.1,
        "desktop runtime is ready"
    );

    if let Err(error) = navigate_to_application(app) {
        if let Err(shutdown_error) = shutdown_supervisor(&state.supervisor) {
            error!(
                error = %shutdown_error,
                "desktop runtime shutdown after navigation failure failed"
            );
        }
        return Err(StartupError::Navigate(error));
    }
    show_main_window(app);
    spawn_runtime_monitor(app.clone());
    Ok(())
}

fn install_supervisor<T>(
    exit_requested: &AtomicBool,
    slot: &Mutex<Option<T>>,
    supervisor: T,
) -> std::result::Result<(), T> {
    let mut slot = slot.lock().expect("desktop supervisor mutex poisoned");
    if exit_requested.load(Ordering::Acquire) {
        return Err(supervisor);
    }
    assert!(
        slot.is_none(),
        "desktop runtime supervisor already installed"
    );
    *slot = Some(supervisor);
    Ok(())
}

fn spawn_runtime_monitor(app: AppHandle) {
    thread::spawn(move || {
        loop {
            thread::sleep(runtime::monitor_interval());
            let state = app.state::<DesktopState>();
            if state.exit_requested.load(Ordering::Acquire) {
                return;
            }

            let failure = {
                let supervisor = state
                    .supervisor
                    .lock()
                    .expect("desktop supervisor mutex poisoned");
                match supervisor.as_ref() {
                    Some(supervisor) => supervisor.check_running().err(),
                    None => return,
                }
            };
            if let Some(error) = failure {
                error!(error = %error, error_debug = ?error, "desktop runtime process exited");
                let supervisor = state
                    .supervisor
                    .lock()
                    .expect("desktop supervisor mutex poisoned")
                    .take();
                drop(supervisor);
                show_failure_window(&app, error.user_summary());
                return;
            }
        }
    });
}

fn navigate_to_application(app: &AppHandle) -> tauri::Result<()> {
    let url = Url::parse(APP_URL).expect("fixed desktop application URL must be valid");
    main_window(app)?.navigate(url)
}

fn show_failure_window(app: &AppHandle, summary: &'static str) {
    let state = app.state::<DesktopState>();
    // Store before touching the window. On an early startup failure the
    // configured shell may not have loaded yet, so it polls this state instead
    // of being redirected away from its pending initial navigation.
    *state
        .startup_failure
        .lock()
        .expect("desktop startup failure mutex poisoned") = Some(summary);
    let local_shell_url = state
        .local_shell_url
        .lock()
        .expect("desktop local shell URL mutex poisoned")
        .clone();
    match main_window(app) {
        Ok(window) => {
            // Once the app has navigated to its HTTP SPA, a later runtime exit
            // must return to the bundled failure shell. During initial startup,
            // `None` deliberately means "leave the configured page load alone."
            if let Some(mut url) = local_shell_url {
                url.query_pairs_mut().append_pair("failure", summary);
                if let Err(error) = window.navigate(url) {
                    error!(error = %error, "navigate to desktop failure page");
                }
            }
            // Show the window even if navigation failed: the shell's status
            // polling still turns an already-loaded page into a useful error.
            let _ = window.unminimize();
            let _ = window.show();
            let _ = window.set_focus();
        }
        Err(error) => {
            error!(error = %error, "show desktop failure window");
        }
    }
}

fn show_main_window(app: &AppHandle) {
    match main_window(app) {
        Ok(window) => {
            let _ = window.unminimize();
            let _ = window.show();
            let _ = window.set_focus();
        }
        Err(error) => warn!(error = %error, "show main window"),
    }
}

fn main_window(app: &AppHandle) -> tauri::Result<WebviewWindow> {
    app.get_webview_window(MAIN_WINDOW_LABEL)
        .ok_or_else(|| tauri::Error::WindowNotFound)
}

fn handle_run_event(app: &AppHandle, event: RunEvent) {
    match event {
        RunEvent::WindowEvent {
            label,
            event: WindowEvent::CloseRequested { api, .. },
            ..
        } if label == MAIN_WINDOW_LABEL => {
            let exiting = app
                .state::<DesktopState>()
                .exit_requested
                .load(Ordering::Acquire);
            if close_disposition(exiting) == CloseDisposition::Hide {
                api.prevent_close();
                if let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) {
                    let _ = window.hide();
                }
            }
        }
        RunEvent::ExitRequested { .. } => {
            shutdown_runtime(app);
        }
        RunEvent::Exit => {
            shutdown_runtime(app);
        }
        _ => {}
    }
}

fn request_exit(app: &AppHandle) {
    let state = app.state::<DesktopState>();
    if state.exit_requested.swap(true, Ordering::AcqRel) {
        return;
    }
    let handle = app.clone();
    thread::spawn(move || {
        shutdown_runtime(&handle);
        handle.exit(0);
    });
}

fn shutdown_runtime(app: &AppHandle) {
    let state = app.state::<DesktopState>();
    state.exit_requested.store(true, Ordering::Release);
    if let Err(error) = shutdown_supervisor(&state.supervisor) {
        error!(error = %error, "desktop runtime shutdown failed");
    }
}

fn shutdown_supervisor(
    slot: &Mutex<Option<RuntimeSupervisor>>,
) -> Result<(), runtime::RuntimeError> {
    let mut supervisor = slot
        .lock()
        .expect("desktop supervisor mutex poisoned")
        .take();
    if let Some(supervisor) = supervisor.as_mut() {
        supervisor.shutdown()?;
    }
    drop(supervisor);
    Ok(())
}

enum DirectoryKind {
    Data,
    Logs,
}

fn open_owned_directory(app: &AppHandle, kind: DirectoryKind) {
    let state = app.state::<DesktopState>();
    let path = match kind {
        DirectoryKind::Data => &state.paths.data,
        DirectoryKind::Logs => &state.paths.logs,
    };
    if let Err(error) = open_directory(path) {
        error!(error = %error, path = %path.display(), "open NovWr directory");
    }
}

#[tauri::command]
fn open_logs(app: AppHandle) -> std::result::Result<(), String> {
    let path = app.state::<DesktopState>().paths.logs.clone();
    open_directory(&path).map_err(|error| error.to_string())
}

#[tauri::command]
fn quit(app: AppHandle) {
    request_exit(&app);
}

#[tauri::command]
fn startup_status(app: AppHandle) -> Option<&'static str> {
    *app.state::<DesktopState>()
        .startup_failure
        .lock()
        .expect("desktop startup failure mutex poisoned")
}

#[derive(Debug, thiserror::Error)]
enum StartupError {
    #[error(transparent)]
    Platform(#[from] platform::UnsupportedWindowsPlatform),
    #[error("create NovWr data and log directories: {0}")]
    CreateDirectories(#[source] std::io::Error),
    #[error("initialize desktop logging: {0}")]
    Logging(#[source] std::io::Error),
    #[error("load persistent desktop secret: {0}")]
    PersistentSecret(#[source] secret::SecretError),
    #[error("resolve bundled desktop runtime directory: {0}")]
    ResourceDirectory(#[source] tauri::Error),
    #[error(transparent)]
    Runtime(#[from] runtime::RuntimeError),
    #[error("navigate to fixed desktop origin: {0}")]
    Navigate(#[source] tauri::Error),
}

impl StartupError {
    fn user_summary(&self) -> &'static str {
        match self {
            Self::Platform(_) => "NovWr 需要 Windows 10（2004 及以上）或 Windows 11 的 x64 版本。",
            Self::CreateDirectories(_) => "无法创建 NovWr 数据目录。",
            Self::Logging(_) => "无法创建 NovWr 日志。",
            Self::PersistentSecret(_) => "桌面安全配置无效。",
            Self::ResourceDirectory(_) => "桌面运行时资源缺失。",
            Self::Runtime(error) => error.user_summary(),
            Self::Navigate(_) => "无法加载本地 NovWr 页面。",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, mpsc};

    #[test]
    fn normal_close_hides_but_explicit_exit_closes() {
        assert_eq!(close_disposition(false), CloseDisposition::Hide);
        assert_eq!(close_disposition(true), CloseDisposition::Exit);
    }

    #[test]
    fn local_shell_url_is_recorded_only_for_tauri_origins() {
        let http_shell =
            Url::parse("http://tauri.localhost/index.html?failure=old#status").unwrap();
        let https_shell = Url::parse("https://tauri.localhost/").unwrap();
        let custom_scheme_shell = Url::parse("tauri://localhost/index.html").unwrap();
        let app = Url::parse(APP_URL).unwrap();
        let initial_blank = Url::parse("about:blank").unwrap();

        assert_eq!(
            normalized_local_shell_url(&http_shell).unwrap().as_str(),
            "http://tauri.localhost/index.html"
        );
        assert_eq!(
            normalized_local_shell_url(&https_shell).unwrap().as_str(),
            "https://tauri.localhost/"
        );
        assert_eq!(
            normalized_local_shell_url(&custom_scheme_shell)
                .unwrap()
                .as_str(),
            "tauri://localhost/index.html"
        );
        assert!(normalized_local_shell_url(&app).is_none());
        assert!(normalized_local_shell_url(&initial_blank).is_none());
    }

    #[test]
    fn supervisor_install_rechecks_exit_after_acquiring_the_slot() {
        let exit_requested = Arc::new(AtomicBool::new(false));
        let slot = Arc::new(Mutex::new(None));
        let slot_guard = slot.lock().expect("test supervisor mutex poisoned");
        let (started_tx, started_rx) = mpsc::channel();

        let install_thread = {
            let exit_requested = Arc::clone(&exit_requested);
            let slot = Arc::clone(&slot);
            thread::spawn(move || {
                started_tx.send(()).expect("signal install attempt");
                install_supervisor(&exit_requested, &slot, 42_u8)
            })
        };

        started_rx.recv().expect("wait for install attempt");
        exit_requested.store(true, Ordering::Release);
        drop(slot_guard);

        assert_eq!(install_thread.join().expect("join install thread"), Err(42));
        assert!(
            slot.lock()
                .expect("test supervisor mutex poisoned")
                .is_none()
        );
    }
}
