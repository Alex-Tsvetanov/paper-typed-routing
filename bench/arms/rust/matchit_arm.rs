//! A C interface to matchit's Router for rbench (arms/matchit.cpp). One router per method.
//! A lookup reports the route id and each captured value as an offset and a length into the
//! query path, so nothing is copied across the boundary.

use matchit::Router;

pub struct Arm {
    routers: Vec<Router<u32>>,
}

#[no_mangle]
pub extern "C" fn rb_matchit_new(methods: u32) -> *mut Arm {
    Box::into_raw(Box::new(Arm { routers: (0..methods).map(|_| Router::new()).collect() }))
}

/// # Safety
/// `arm` comes from rb_matchit_new and is not used afterwards.
#[no_mangle]
pub unsafe extern "C" fn rb_matchit_free(arm: *mut Arm) {
    if !arm.is_null() {
        drop(Box::from_raw(arm));
    }
}

/// Returns 0, or 1 with a NUL-terminated message in `err`.
///
/// # Safety
/// `pattern` points at `len` bytes of UTF-8; `err` at `errcap` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn rb_matchit_insert(
    arm: *mut Arm, method: u32, pattern: *const u8, len: usize, id: u32, err: *mut u8, errcap: usize,
) -> i32 {
    let arm = &mut *arm;
    let text = match std::str::from_utf8(std::slice::from_raw_parts(pattern, len)) {
        Ok(t) => t,
        Err(_) => return 1,
    };
    match arm.routers[method as usize].insert(text, id) {
        Ok(()) => 0,
        Err(e) => {
            let msg = e.to_string();
            let n = msg.len().min(errcap.saturating_sub(1));
            std::ptr::copy_nonoverlapping(msg.as_ptr(), err, n);
            *err.add(n) = 0;
            1
        }
    }
}

/// Returns the route id, or u32::MAX for no match. Writes up to `max` captured values as
/// (offset, length) pairs into `caps` and their count into `ncaps`.
///
/// # Safety
/// `path` points at `len` bytes of UTF-8 that outlive the call; `caps` at 2 * `max` u32s.
/// The path is taken as UTF-8 without a check, as a Rust server receives it: http::Uri has
/// already validated it.
#[no_mangle]
pub unsafe extern "C" fn rb_matchit_at(
    arm: *const Arm, method: u32, path: *const u8, len: usize, caps: *mut u32, max: u32, ncaps: *mut u32,
) -> u32 {
    let arm = &*arm;
    let text = std::str::from_utf8_unchecked(std::slice::from_raw_parts(path, len));
    match arm.routers[method as usize].at(text) {
        Ok(m) => {
            let mut n: u32 = 0;
            for (_, v) in m.params.iter() {
                if n == max {
                    break;
                }
                *caps.add(2 * n as usize) = (v.as_ptr() as usize - path as usize) as u32;
                *caps.add(2 * n as usize + 1) = v.len() as u32;
                n += 1;
            }
            *ncaps = n;
            *m.value
        }
        Err(_) => {
            *ncaps = 0;
            u32::MAX
        }
    }
}
