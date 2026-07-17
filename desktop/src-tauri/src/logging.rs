use std::io;
use std::path::Path;

use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::util::SubscriberInitExt;

pub struct DesktopLogGuard {
    _guard: WorkerGuard,
}

pub fn initialize(log_directory: &Path) -> io::Result<DesktopLogGuard> {
    let appender = tracing_appender::rolling::never(log_directory, "desktop.log");
    let (writer, guard) = tracing_appender::non_blocking(appender);
    tracing_subscriber::fmt()
        .with_ansi(false)
        .with_target(false)
        .with_writer(writer)
        .finish()
        .try_init()
        .map_err(|error| io::Error::other(format!("initialize desktop logging: {error}")))?;
    Ok(DesktopLogGuard { _guard: guard })
}
