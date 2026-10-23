//! The null router: every request is route 0 with no captured values. It never reads the path,
//! so it measures the server alone (bench/arms/null.cpp is its round 2 counterpart).

use crate::{Captures, Lookup};

pub struct NullArm;

impl Lookup for NullArm {
    type Scratch = ();

    #[inline]
    fn lookup<'a>(&self, _scratch: &mut (), _path: &'a str, _caps: &mut Captures<'a>) -> Option<u32> {
        Some(0)
    }
}
