//! Tao 0.35's macOS delegate handles `applicationWillTerminate:` but does not
//! expose `applicationShouldTerminate:`. Cocoa Quit (Cmd+Q/Dock/OS) consequently
//! bypasses Tauri's ExitRequested event. Install that one missing delegate method
//! and route normal termination through our save handshake. Other delegate
//! behaviour remains owned by Tao. Revisit this adapter when upgrading Tao.

use std::ffi::{c_char, c_void};
use std::sync::OnceLock;

use anyhow::{Result, ensure};

type Object = *mut c_void;
type ShouldTerminate = extern "C" fn(Object, Object, Object) -> usize;
static ON_QUIT: OnceLock<Box<dyn Fn() + Send + Sync>> = OnceLock::new();

#[link(name = "objc")]
unsafe extern "C" {
    fn objc_getClass(name: *const c_char) -> Object;
    fn sel_registerName(name: *const c_char) -> Object;
    fn objc_msgSend(receiver: Object, selector: Object) -> Object;
    fn object_getClass(object: Object) -> Object;
    fn class_getInstanceMethod(class: Object, selector: Object) -> Object;
    fn class_addMethod(
        class: Object,
        selector: Object,
        implementation: ShouldTerminate,
        encoding: *const c_char,
    ) -> bool;
}

extern "C" fn should_terminate(_: Object, _: Object, _: Object) -> usize {
    if let Some(on_quit) = ON_QUIT.get() {
        on_quit();
    }
    // NSTerminateCancel. On acknowledgement, AppHandle::exit leaves the event
    // loop directly; it does not send Cocoa's terminate: message recursively.
    0
}

/// Must run once, on the main thread after Tauri creates its application delegate.
pub fn install(on_quit: impl Fn() + Send + Sync + 'static) -> Result<()> {
    // These two selectors are Objective-C getters returning object pointers.
    // The installed method's `Q@:@` encoding is NSUInteger(self, SEL, NSApplication*)
    // on the supported 64-bit Apple Silicon platform.
    unsafe {
        let class = objc_getClass(c"NSApplication".as_ptr());
        ensure!(!class.is_null(), "NSApplication class is unavailable");
        let app = objc_msgSend(class, sel_registerName(c"sharedApplication".as_ptr()));
        let delegate = objc_msgSend(app, sel_registerName(c"delegate".as_ptr()));
        ensure!(
            !delegate.is_null(),
            "Tauri application delegate is unavailable"
        );
        let delegate_class = object_getClass(delegate);
        let selector = sel_registerName(c"applicationShouldTerminate:".as_ptr());
        ensure!(
            class_getInstanceMethod(delegate_class, selector).is_null(),
            "Tauri now implements applicationShouldTerminate:; update the quit adapter"
        );
        ensure!(
            ON_QUIT.set(Box::new(on_quit)).is_ok(),
            "quit adapter already installed"
        );
        ensure!(
            class_addMethod(delegate_class, selector, should_terminate, c"Q@:@".as_ptr()),
            "could not install save-before-quit delegate"
        );
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    #[test]
    fn cocoa_quit_is_deferred_and_repeated_requests_reach_the_protocol() {
        static CALLS: AtomicUsize = AtomicUsize::new(0);
        assert!(
            ON_QUIT
                .set(Box::new(|| {
                    CALLS.fetch_add(1, Ordering::SeqCst);
                }))
                .is_ok()
        );
        for _ in 0..3 {
            assert_eq!(
                should_terminate(
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut()
                ),
                0
            );
        }
        assert_eq!(CALLS.load(Ordering::SeqCst), 3);
    }
}
