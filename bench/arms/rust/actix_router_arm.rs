//! A C interface to actix-router's Router for rbench (arms/actix_router.cpp). One Router per
//! method. A lookup matches a Path over &str, so nothing is percent-decoded, and reports the
//! route id and each captured value as an offset and a length into the query path, so
//! nothing is copied across the boundary.
//!
//! The arm keeps one Path and sets it to each query path (Path::set clears the captured
//! segments and keeps their vector's capacity), so a lookup does not allocate a new segment
//! vector for every query.

use actix_router::{Path, ResourceDef, Router, RouterBuilder};

pub struct Arm {
    building: Vec<RouterBuilder<u32>>,
    routers: Vec<Router<u32>>,
    /// The query path of the last lookup. It is 'static only for the type: it points into
    /// the caller's path, which outlives one rb_actix_at call, and is never read after it.
    path: Path<&'static str>,
}

#[no_mangle]
pub extern "C" fn rb_actix_new(methods: u32) -> *mut Arm {
    Box::into_raw(Box::new(Arm {
        building: (0..methods).map(|_| Router::build()).collect(),
        routers: Vec::new(),
        path: Path::new(""),
    }))
}

/// # Safety
/// `arm` comes from rb_actix_new and is not used afterwards.
#[no_mangle]
pub unsafe extern "C" fn rb_actix_free(arm: *mut Arm) {
    if !arm.is_null() {
        drop(Box::from_raw(arm));
    }
}

/// Appends a route to its method's routing list (ResourceDef::new). Returns 0, or 1 with a
/// NUL-terminated message in `err`. ResourceDef::new panics on a malformed pattern, which
/// aborts the process (panic = "abort"): the caller passes only patterns it has checked.
///
/// # Safety
/// `pattern` points at `len` bytes; `err` at `errcap` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn rb_actix_insert(
    arm: *mut Arm, method: u32, pattern: *const u8, len: usize, id: u32, err: *mut u8, errcap: usize,
) -> i32 {
    let arm = &mut *arm;
    let text = match std::str::from_utf8(std::slice::from_raw_parts(pattern, len)) {
        Ok(t) => t,
        Err(_) => {
            let msg = b"pattern is not UTF-8";
            let n = msg.len().min(errcap.saturating_sub(1));
            std::ptr::copy_nonoverlapping(msg.as_ptr(), err, n);
            *err.add(n) = 0;
            return 1;
        }
    };
    arm.building[method as usize].rdef(ResourceDef::new(text), id);
    0
}

/// Finishes the routing lists into routers (RouterBuilder::finish).
///
/// # Safety
/// `arm` comes from rb_actix_new.
#[no_mangle]
pub unsafe extern "C" fn rb_actix_finalize(arm: *mut Arm) {
    let arm = &mut *arm;
    arm.routers = std::mem::take(&mut arm.building).into_iter().map(|b| b.finish()).collect();
}

/// Returns the route id of the first route of the method's list that matches, or u32::MAX.
/// Writes up to `max` captured values as (offset, length) pairs into `caps` and their count
/// into `ncaps`.
///
/// # Safety
/// `arm` has been finalized; `path` points at `len` bytes of UTF-8 that outlive the call;
/// `caps` at 2 * `max` u32s. The path is taken as UTF-8 without a check, as for matchit.
#[no_mangle]
pub unsafe extern "C" fn rb_actix_at(
    arm: *mut Arm, method: u32, path: *const u8, len: usize, caps: *mut u32, max: u32, ncaps: *mut u32,
) -> u32 {
    let arm = &mut *arm;
    let text: &str = std::str::from_utf8_unchecked(std::slice::from_raw_parts(path, len));
    arm.path.set(std::mem::transmute::<&str, &'static str>(text));
    match arm.routers[method as usize].recognize(&mut arm.path) {
        Some((id, _)) => {
            let mut n: u32 = 0;
            for (_, v) in arm.path.iter() {
                if n == max {
                    break;
                }
                *caps.add(2 * n as usize) = (v.as_ptr() as usize - path as usize) as u32;
                *caps.add(2 * n as usize + 1) = v.len() as u32;
                n += 1;
            }
            *ncaps = n;
            *id
        }
        None => {
            *ncaps = 0;
            u32::MAX
        }
    }
}
