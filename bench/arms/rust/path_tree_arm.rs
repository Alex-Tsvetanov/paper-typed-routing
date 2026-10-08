//! A C interface to path-tree's PathTree for rbench (arms/path_tree.cpp). One tree per method.
//! A lookup reports the route id and each captured value as an offset and a length into the
//! query path (path-tree's raw values are slices of it), so nothing is copied across the
//! boundary.

use path_tree::PathTree;

pub struct Arm {
    trees: Vec<PathTree<u32>>,
}

#[no_mangle]
pub extern "C" fn rb_path_tree_new(methods: u32) -> *mut Arm {
    Box::into_raw(Box::new(Arm { trees: (0..methods).map(|_| PathTree::new()).collect() }))
}

/// # Safety
/// `arm` comes from rb_path_tree_new and is not used afterwards.
#[no_mangle]
pub unsafe extern "C" fn rb_path_tree_free(arm: *mut Arm) {
    if !arm.is_null() {
        drop(Box::from_raw(arm));
    }
}

/// Returns 0, or 1 if the pattern is not UTF-8. PathTree::insert has no error of its own.
///
/// # Safety
/// `pattern` points at `len` bytes.
#[no_mangle]
pub unsafe extern "C" fn rb_path_tree_insert(arm: *mut Arm, method: u32, pattern: *const u8, len: usize, id: u32) -> i32 {
    let arm = &mut *arm;
    match std::str::from_utf8(std::slice::from_raw_parts(pattern, len)) {
        Ok(text) => {
            let _ = arm.trees[method as usize].insert(text, id);
            0
        }
        Err(_) => 1,
    }
}

/// Returns the route id, or u32::MAX for no match. Writes up to `max` captured values as
/// (offset, length) pairs into `caps` and their count into `ncaps`.
///
/// # Safety
/// `path` points at `len` bytes of UTF-8 that outlive the call; `caps` at 2 * `max` u32s.
/// The path is taken as UTF-8 without a check, as a Rust server receives it.
#[no_mangle]
pub unsafe extern "C" fn rb_path_tree_find(
    arm: *const Arm, method: u32, path: *const u8, len: usize, caps: *mut u32, max: u32, ncaps: *mut u32,
) -> u32 {
    let arm = &*arm;
    let text = std::str::from_utf8_unchecked(std::slice::from_raw_parts(path, len));
    match arm.trees[method as usize].find(text) {
        Some((value, p)) => {
            let mut n: u32 = 0;
            for v in p.raws.iter() {
                if n == max {
                    break;
                }
                *caps.add(2 * n as usize) = (v.as_ptr() as usize - path as usize) as u32;
                *caps.add(2 * n as usize + 1) = v.len() as u32;
                n += 1;
            }
            *ncaps = n;
            *value
        }
        None => {
            *ncaps = 0;
            u32::MAX
        }
    }
}
