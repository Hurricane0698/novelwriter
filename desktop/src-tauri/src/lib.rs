#[cfg(target_os = "windows")]
mod desktop_app;
#[cfg(target_os = "windows")]
mod logging;
mod paths;
#[cfg(target_os = "windows")]
mod platform;
#[cfg(target_os = "windows")]
mod runtime;
mod secret;

#[cfg(target_os = "windows")]
mod windows;

#[cfg(target_os = "windows")]
pub fn run() {
    desktop_app::run();
}

#[cfg(not(target_os = "windows"))]
pub fn run() {
    panic!("NovWr desktop shell supports Windows x64 only");
}
