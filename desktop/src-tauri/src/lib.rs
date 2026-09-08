#[cfg(any(target_os = "windows", target_os = "macos"))]
mod desktop_app;
#[cfg(any(target_os = "windows", target_os = "macos"))]
mod logging;
mod paths;
#[cfg(any(target_os = "windows", target_os = "macos"))]
mod platform;
#[cfg(any(target_os = "windows", target_os = "macos"))]
mod runtime;
mod secret;

#[cfg(target_os = "windows")]
mod windows;

#[cfg(target_os = "macos")]
mod macos;

#[cfg(any(target_os = "windows", target_os = "macos"))]
pub fn run() {
    // The process guardian must enter its non-UI mode before touching Cocoa/Tauri.
    #[cfg(target_os = "macos")]
    if let Some(code) = macos::run_guardian_if_requested() {
        std::process::exit(code);
    }
    desktop_app::run();
}

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub fn run() {
    panic!("NovWr desktop shell supports Windows x64 and Apple Silicon macOS");
}
