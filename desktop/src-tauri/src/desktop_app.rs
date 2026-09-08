use std::io;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;

use anyhow::{Context, Result as AnyResult};
#[cfg(target_os = "macos")]
use tauri::menu::{HELP_SUBMENU_ID, MenuItemKind};
use tauri::menu::{Menu, MenuItem};
#[cfg(target_os = "windows")]
use tauri::tray::{TrayIcon, TrayIconBuilder};
use tauri::webview::PageLoadPayload;
use tauri::{App, AppHandle, Manager, RunEvent, Url, WebviewWindow, WindowEvent};
use tracing::{error, info, warn};

use crate::logging::{self, DesktopLogGuard};
use crate::paths::{AppPaths, DATA_ROOT_OVERRIDE_ENV};
use crate::platform;
use crate::platform::open_directory;
use crate::platform::single_instance::{Acquisition, acquire};
use crate::runtime::{self, APP_URL, RuntimeSupervisor};
use crate::secret;

const MAIN_WINDOW_LABEL: &str = "main";
const TRAY_OPEN_ID: &str = "open";
const TRAY_DATA_ID: &str = "open-data";
const TRAY_LOGS_ID: &str = "open-logs";
const TRAY_QUIT_ID: &str = "quit";

fn startup_failure_title(summary: &str) -> String {
    format!("NovWr — 启动失败：{summary}")
}

struct DesktopState {
    paths: AppPaths,
    // `WebviewWindow::url()` is still `about:blank` during `setup`. Capture the
    // bundled shell URL from the page-load hook instead so failure navigation
    // can never turn `about:blank` into an inert white page.
    local_shell_url: Mutex<Option<Url>>,
    supervisor: Mutex<Option<RuntimeSupervisor>>,
    #[cfg(target_os = "windows")]
    tray: Mutex<Option<TrayIcon>>,
    log_guard: Mutex<Option<DesktopLogGuard>>,
    exit_requested: AtomicBool,
    shutdown_complete: AtomicBool,
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
            #[cfg(target_os = "windows")]
            tray: Mutex::new(None),
            log_guard: Mutex::new(None),
            exit_requested: AtomicBool::new(false),
            shutdown_complete: AtomicBool::new(false),
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
    #[cfg(not(target_os = "macos"))]
    let context = tauri::generate_context!();
    #[cfg(target_os = "macos")]
    let context = {
        let mut context = tauri::generate_context!();
        isolate_override_webviews(
            context.config_mut(),
            std::env::var_os(DATA_ROOT_OVERRIDE_ENV).is_some(),
        );
        context
    };
    let mut primary = match acquire(&context.config().identifier)
        .expect("acquire NovWr desktop single-instance gate")
    {
        Acquisition::Primary(primary) => primary,
        Acquisition::Secondary => return,
    };

    let builder = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![open_logs, quit, startup_status])
        .on_page_load(handle_page_load)
        .setup(|app| setup(app).map_err(Into::into));
    #[cfg(target_os = "macos")]
    let builder = builder.menu(build_macos_menu);
    let app = builder
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
        .expect("release NovWr desktop single-instance gate");
}

#[cfg(target_os = "macos")]
fn isolate_override_webviews(config: &mut tauri::Config, has_data_root_override: bool) {
    if has_data_root_override {
        // WKWebView cannot redirect data_directory to this profile. A non-persistent
        // store keeps isolated runtime validation out of the user's normal WebKit data.
        for window in &mut config.app.windows {
            window.incognito = true;
        }
    }
}

fn setup(app: &mut App) -> AnyResult<()> {
    app.get_webview_window(MAIN_WINDOW_LABEL)
        .context("configured main window is missing")?;
    let local_data_root = app
        .path()
        .local_data_dir()
        .context("resolve local application data directory")?;
    #[cfg(target_os = "windows")]
    let defaults = AppPaths::from_local_data_root(local_data_root);
    #[cfg(target_os = "macos")]
    let defaults = AppPaths::from_macos_roots(
        local_data_root,
        app.path()
            .home_dir()
            .context("resolve user home directory")?
            .join("Library/Logs"),
    );
    let override_value = std::env::var_os(DATA_ROOT_OVERRIDE_ENV);
    let (paths, invalid_override) = match defaults.with_root_override(override_value.as_deref()) {
        Ok(paths) => (paths, false),
        Err(error) => {
            eprintln!("NovWr desktop path configuration: {error}");
            (defaults, true)
        }
    };
    app.manage(DesktopState::new(paths));

    #[cfg(target_os = "windows")]
    {
        let tray = build_tray(app).context("create NovWr tray icon")?;
        *app.state::<DesktopState>()
            .tray
            .lock()
            .expect("desktop tray mutex poisoned") = Some(tray);
    }

    if invalid_override {
        show_failure_window(
            app.handle(),
            "桌面数据目录设置无效：NOVWR_DESKTOP_DATA_ROOT 必须是绝对路径。",
        );
        return Ok(());
    }

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

#[cfg(target_os = "windows")]
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
        .on_menu_event(handle_shell_menu)
        .build(app)
}

#[cfg(target_os = "macos")]
fn build_macos_menu(app: &AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    // Tauri's native menu provides About/Hide/Quit, standard Cmd editing actions,
    // fullscreen and window commands, including the Cocoa responder chain.
    let menu = Menu::default(app)?;
    if let Some(MenuItemKind::Submenu(help)) = menu.get(HELP_SUBMENU_ID) {
        help.append_items(&[
            &MenuItem::with_id(app, TRAY_OPEN_ID, "打开 NovWr", true, None::<&str>)?,
            &MenuItem::with_id(app, TRAY_DATA_ID, "打开数据目录", true, None::<&str>)?,
            &MenuItem::with_id(app, TRAY_LOGS_ID, "打开日志", true, None::<&str>)?,
        ])?;
    }
    Ok(menu)
}

fn handle_shell_menu(app: &AppHandle, event: tauri::menu::MenuEvent) {
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
    platform::require_supported().map_err(StartupError::Platform)?;

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
            if let Err(error) = window.set_title(&startup_failure_title(summary)) {
                error!(error = %error, "set desktop failure window title");
            }
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
            reveal_window(app, &window);
        }
        Err(error) => {
            error!(error = %error, "show desktop failure window");
        }
    }
}

fn show_main_window(app: &AppHandle) {
    match main_window(app) {
        Ok(window) => {
            reveal_window(app, &window);
        }
        Err(error) => warn!(error = %error, "show main window"),
    }
}

fn reveal_window(app: &AppHandle, window: &WebviewWindow) {
    // Cmd+H hides the application as well as the window. Dock/secondary-launch
    // activation must unhide that layer before focusing the existing webview.
    #[cfg(target_os = "macos")]
    let _ = app.show();
    #[cfg(target_os = "windows")]
    let _ = app;
    let _ = window.unminimize();
    let _ = window.show();
    let _ = window.set_focus();
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
        #[cfg(target_os = "macos")]
        RunEvent::Reopen { .. } => show_main_window(app),
        #[cfg(target_os = "macos")]
        RunEvent::MenuEvent(event) => handle_shell_menu(app, event),
        RunEvent::ExitRequested { api, .. } => {
            // Keep the event loop responsive during process shutdown, and prevent
            // repeated Cmd+Q/OS quit requests from bypassing the same cleanup.
            if !app
                .state::<DesktopState>()
                .shutdown_complete
                .load(Ordering::Acquire)
            {
                api.prevent_exit();
                request_exit(app);
            }
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
    state.shutdown_complete.store(true, Ordering::Release);
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
    Platform(#[from] platform::UnsupportedPlatform),
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
            Self::Platform(error) => error.user_summary(),
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

    #[cfg(target_os = "macos")]
    #[test]
    fn isolated_data_roots_do_not_use_the_normal_webkit_store() {
        let mut config = tauri::Config::default();
        config
            .app
            .windows
            .push(tauri::utils::config::WindowConfig::default());
        isolate_override_webviews(&mut config, false);
        assert!(config.app.windows.iter().all(|window| !window.incognito));
        isolate_override_webviews(&mut config, true);
        assert!(config.app.windows.iter().all(|window| window.incognito));
    }

    #[test]
    fn startup_failure_title_exposes_the_actionable_summary() {
        assert_eq!(
            startup_failure_title("本地端口 8000 已被占用。"),
            "NovWr — 启动失败：本地端口 8000 已被占用。"
        );
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
