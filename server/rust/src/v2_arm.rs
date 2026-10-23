//! RegexMatcher v2 as a router of the server, through the C interface of server/capi/p2v2.h
//! (feature `v2`; build.rs links the static library p2v2_c). It is the code of the C++ server's v2
//! arm, compiled with that server's compiler and flags; only the language boundary differs, and it
//! counts against v2.
//!
//! The patterns go in as the file has them, in rbench's syntax (`{p0}`, `{*p0}`), with no
//! conversion, route i being line i. A lookup is one `p2v2_find` call with method 0 (GET) and the
//! path's bytes; the captured values come back as (offset, length) pairs into the path, and are
//! taken as slices of it. Nothing is copied.

use std::ffi::{c_char, c_uint};

use crate::routes::{Route, MAX_PARAMS};
use crate::{Captures, Lookup};

/// P2V2_NO_ROUTE.
const NO_ROUTE: u32 = 0xFFFF_FFFF;
/// The size of the message buffer for a refused table.
const ERR_CAP: usize = 512;

#[repr(C)]
struct Table {
    _opaque: [u8; 0],
}

extern "C" {
    fn p2v2_build(patterns: *const *const c_char, lens: *const usize, n: usize, err: *mut c_char, errcap: usize) -> *mut Table;
    fn p2v2_free(table: *mut Table);
    fn p2v2_find(
        table: *const Table, method: c_uint, path: *const c_char, len: usize, caps: *mut u32, max_caps: u32, ncaps: *mut u32,
    ) -> u32;
}

pub struct V2Arm {
    table: *mut Table,
}

// SAFETY: the table is built once and p2v2_find only reads it (it takes a const table).
unsafe impl Send for V2Arm {}
unsafe impl Sync for V2Arm {}

impl Drop for V2Arm {
    fn drop(&mut self) {
        // SAFETY: `table` came from p2v2_build and is not used afterwards.
        unsafe { p2v2_free(self.table) }
    }
}

impl V2Arm {
    /// Route i gets id i. A table v2 does not build is reported with the library's message.
    pub fn build(routes: &[Route]) -> Result<Self, String> {
        let patterns: Vec<*const c_char> = routes.iter().map(|r| r.text.as_ptr().cast()).collect();
        let lens: Vec<usize> = routes.iter().map(|r| r.text.len()).collect();
        let mut err = [0 as c_char; ERR_CAP];
        // SAFETY: `patterns` and `lens` hold n entries, each pattern valid for its length for the
        // call; `err` has ERR_CAP writable bytes.
        let table = unsafe { p2v2_build(patterns.as_ptr(), lens.as_ptr(), routes.len(), err.as_mut_ptr(), ERR_CAP) };
        if table.is_null() {
            // SAFETY: p2v2_build terminates the message it writes; the buffer starts zeroed.
            let msg = unsafe { std::ffi::CStr::from_ptr(err.as_ptr()) }.to_string_lossy().into_owned();
            return Err(format!("v2 refuses the routes: {msg}"));
        }
        Ok(Self { table })
    }
}

impl Lookup for V2Arm {
    type Scratch = ();

    #[inline]
    fn lookup<'a>(&self, _scratch: &mut (), path: &'a str, caps: &mut Captures<'a>) -> Option<u32> {
        let mut pairs = [0u32; 2 * MAX_PARAMS];
        let mut n: u32 = 0;
        // SAFETY: `path` is valid for its length; `pairs` has 2 * MAX_PARAMS entries.
        let id = unsafe {
            p2v2_find(self.table, 0, path.as_ptr().cast(), path.len(), pairs.as_mut_ptr(), MAX_PARAMS as u32, &mut n)
        };
        if id == NO_ROUTE {
            return None;
        }
        for pair in pairs.chunks_exact(2).take(n as usize) {
            let (start, len) = (pair[0] as usize, pair[1] as usize);
            caps.push(&path[start..start + len]);
        }
        Some(id)
    }
}
