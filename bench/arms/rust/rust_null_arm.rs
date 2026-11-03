//! The rust-null arm of design/review-runs/boundary-arms.md (arms/rust_null.cpp): an empty Rust function
//! behind the Rust arms' C interface, with the shape of rb_matchit_at (matchit_arm.rs) and no router. It
//! reads the path's length and returns route 0 or 1, as the C++ null arms' lookups do, so the arm's time per
//! lookup is the harness's loop, the adapter and one call across the Rust boundary: the null that the Rust
//! arms' times are taken net of.

use std::ffi::c_void;

/// Returns route 0 or 1 (the path's length modulo 2) and no captured value.
///
/// # Safety
/// `ncaps` points at a writable u32. Nothing else is read.
#[no_mangle]
pub unsafe extern "C" fn rb_rust_null_at(
    _arm: *const c_void, _method: u32, _path: *const u8, len: usize, _caps: *mut u32, _max: u32, ncaps: *mut u32,
) -> u32 {
    *ncaps = 0;
    (len & 1) as u32
}
