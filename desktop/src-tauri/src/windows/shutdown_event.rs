use std::ffi::{OsStr, OsString};
use std::io;
use std::iter;
use std::os::windows::ffi::OsStrExt;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
use std::process;

use windows_sys::Win32::Foundation::{
    ERROR_ALREADY_EXISTS, GetLastError, HANDLE, WAIT_FAILED, WAIT_OBJECT_0, WAIT_TIMEOUT,
};
use windows_sys::Win32::System::Threading::{CreateEventW, SetEvent, WaitForSingleObject};

const EVENT_NAME_RANDOM_BYTES: usize = 16;
const EVENT_NAME_PREFIX: &str = r"Local\io.github.hurricane0698.novwr.desktop-shutdown";

#[derive(Debug)]
pub struct ShutdownEvent {
    handle: OwnedHandle,
    name: OsString,
}

impl ShutdownEvent {
    pub fn create() -> io::Result<Self> {
        let name = unique_event_name()?;
        let encoded_name = encode_nul_terminated(&name)?;
        let raw_handle = unsafe { CreateEventW(std::ptr::null(), 1, 0, encoded_name.as_ptr()) };
        if raw_handle.is_null() {
            return Err(last_operation_error("CreateEventW(desktop shutdown)"));
        }
        let already_existed = unsafe { GetLastError() } == ERROR_ALREADY_EXISTS;
        let handle = unsafe { OwnedHandle::from_raw_handle(raw_handle.cast()) };
        if already_existed {
            return Err(io::Error::new(
                io::ErrorKind::AlreadyExists,
                "generated desktop shutdown event name already exists",
            ));
        }

        Ok(Self { handle, name })
    }

    pub fn name(&self) -> &OsStr {
        &self.name
    }

    pub fn signal(&self) -> io::Result<()> {
        if unsafe { SetEvent(self.raw_handle()) } == 0 {
            return Err(last_operation_error("SetEvent(desktop shutdown)"));
        }
        Ok(())
    }

    #[cfg(test)]
    fn is_signaled(&self) -> io::Result<bool> {
        match unsafe { WaitForSingleObject(self.raw_handle(), 0) } {
            WAIT_OBJECT_0 => Ok(true),
            WAIT_TIMEOUT => Ok(false),
            WAIT_FAILED => Err(last_operation_error(
                "WaitForSingleObject(desktop shutdown)",
            )),
            status => Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!(
                    "WaitForSingleObject(desktop shutdown) returned unexpected status {status}"
                ),
            )),
        }
    }

    fn raw_handle(&self) -> HANDLE {
        self.handle.as_raw_handle().cast()
    }
}

fn unique_event_name() -> io::Result<OsString> {
    let mut random_bytes = [0_u8; EVENT_NAME_RANDOM_BYTES];
    getrandom::fill(&mut random_bytes).map_err(|error| {
        io::Error::other(format!(
            "obtain randomness for desktop shutdown event name: {error}"
        ))
    })?;
    Ok(OsString::from(format!(
        "{EVENT_NAME_PREFIX}.{}.{}",
        process::id(),
        hex::encode(random_bytes)
    )))
}

fn encode_nul_terminated(value: &OsStr) -> io::Result<Vec<u16>> {
    let encoded: Vec<u16> = value.encode_wide().chain(iter::once(0)).collect();
    if encoded[..encoded.len() - 1].contains(&0) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "desktop shutdown event name contains an embedded NUL",
        ));
    }
    Ok(encoded)
}

fn last_operation_error(operation: &'static str) -> io::Error {
    let source = io::Error::from_raw_os_error(unsafe { GetLastError() } as i32);
    io::Error::new(source.kind(), format!("{operation}: {source}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manual_reset_event_stays_signaled_after_signal() {
        let event = ShutdownEvent::create().expect("create shutdown event");

        assert!(!event.is_signaled().expect("inspect initial event state"));
        event.signal().expect("signal shutdown event");
        assert!(event.is_signaled().expect("inspect signaled event state"));
        assert!(
            event
                .is_signaled()
                .expect("manual-reset event must remain signaled")
        );
    }

    #[test]
    fn each_shutdown_event_has_a_unique_name() {
        let first = ShutdownEvent::create().expect("create first shutdown event");
        let second = ShutdownEvent::create().expect("create second shutdown event");

        assert!(
            first
                .name()
                .to_string_lossy()
                .starts_with(r"Local\io.github.hurricane0698.novwr.desktop-shutdown.")
        );
        assert_ne!(first.name(), second.name());
    }
}
