use std::ffi::OsStr;
use std::io;
use std::os::windows::ffi::OsStrExt;
use std::path::Path;

use windows_sys::Win32::UI::Shell::ShellExecuteW;
use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;

pub fn open_directory(path: &Path) -> io::Result<()> {
    if !path.is_absolute() || !path.is_dir() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("directory must exist and be absolute: {}", path.display()),
        ));
    }

    let operation = encode_wide(OsStr::new("open"))?;
    let target = encode_wide(path.as_os_str())?;
    let result = unsafe {
        ShellExecuteW(
            std::ptr::null_mut(),
            operation.as_ptr(),
            target.as_ptr(),
            std::ptr::null(),
            std::ptr::null(),
            SW_SHOWNORMAL,
        )
    };
    if result as isize <= 32 {
        return Err(io::Error::other(format!(
            "ShellExecuteW failed with code {}",
            result as isize
        )));
    }
    Ok(())
}

fn encode_wide(value: &OsStr) -> io::Result<Vec<u16>> {
    let mut encoded: Vec<u16> = value.encode_wide().collect();
    if encoded.contains(&0) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "shell path contains an embedded NUL",
        ));
    }
    encoded.push(0);
    Ok(encoded)
}
