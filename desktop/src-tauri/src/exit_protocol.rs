/// Correlate replies so a timed-out/cancelled save cannot approve a later quit.
#[derive(Default)]
pub(crate) struct ExitProtocol {
    next_id: u64,
    pending: Option<u64>,
}

impl ExitProtocol {
    pub fn request(&mut self) -> Option<u64> {
        if self.pending.is_some() {
            return None;
        }
        self.next_id += 1;
        self.pending = Some(self.next_id);
        self.pending
    }

    pub fn complete(&mut self, id: u64) -> bool {
        if self.pending != Some(id) {
            return false;
        }
        self.pending = None;
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repeated_quit_does_not_bypass_pending_save() {
        let mut protocol = ExitProtocol::default();
        let id = protocol.request().unwrap();
        assert!(protocol.request().is_none());
        assert!(!protocol.complete(id + 1));
        assert!(protocol.complete(id));
        assert!(!protocol.complete(id));
    }

    #[test]
    fn cancelled_or_timed_out_reply_cannot_approve_new_request() {
        let mut protocol = ExitProtocol::default();
        let first = protocol.request().unwrap();
        assert!(protocol.complete(first));
        let second = protocol.request().unwrap();
        assert_ne!(first, second);
        assert!(!protocol.complete(first));
        assert!(protocol.complete(second));
    }
}
