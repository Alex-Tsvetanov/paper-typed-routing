//! The stop signals: SIGTERM and SIGINT on Unix, Ctrl-C and Ctrl-Break on Windows. They are
//! registered before the listening socket opens, so a signal sent once the server accepts is
//! never lost.

use std::io;

#[cfg(unix)]
pub struct Stop {
    term: tokio::signal::unix::Signal,
    int: tokio::signal::unix::Signal,
}

#[cfg(unix)]
impl Stop {
    pub fn new() -> io::Result<Self> {
        use tokio::signal::unix::{signal, SignalKind};
        Ok(Self { term: signal(SignalKind::terminate())?, int: signal(SignalKind::interrupt())? })
    }

    /// Completes when one of the signals arrives.
    pub async fn wait(&mut self) {
        tokio::select! {
            _ = self.term.recv() => {}
            _ = self.int.recv() => {}
        }
    }
}

#[cfg(windows)]
pub struct Stop {
    ctrl_c: tokio::signal::windows::CtrlC,
    ctrl_break: tokio::signal::windows::CtrlBreak,
}

#[cfg(windows)]
impl Stop {
    pub fn new() -> io::Result<Self> {
        Ok(Self { ctrl_c: tokio::signal::windows::ctrl_c()?, ctrl_break: tokio::signal::windows::ctrl_break()? })
    }

    /// Completes when one of the signals arrives.
    pub async fn wait(&mut self) {
        tokio::select! {
            _ = self.ctrl_c.recv() => {}
            _ = self.ctrl_break.recv() => {}
        }
    }
}
