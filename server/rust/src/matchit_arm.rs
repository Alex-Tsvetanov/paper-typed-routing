//! matchit 0.9.2 as a router of the server. It follows round 2's arm: the pattern text is
//! `render` (bench/arms/matchit.cpp, `add`: `{name}` and `{*name}`, the root as `/`), the build
//! is `Router::insert` per route (bench/arms/rust/matchit_arm.rs, `rb_matchit_insert`) and the
//! lookup is `Router::at` with the captured values taken from `m.params` in pattern order
//! (`rb_matchit_at`). Round 2 kept one router per method; the routes file is GET only, so
//! there is one. Nothing is copied: the values are slices of the request path.

use matchit::Router;

use crate::routes::Route;
use crate::{Captures, Lookup};

pub struct MatchitArm {
    router: Router<u32>,
}

impl MatchitArm {
    /// Route i gets id i. A route matchit refuses (a conflict) is reported with its index.
    pub fn build(routes: &[Route]) -> Result<Self, String> {
        let mut router = Router::new();
        for (id, route) in routes.iter().enumerate() {
            router.insert(route.render(), id as u32).map_err(|e| format!("matchit refuses route {id}: {e}"))?;
        }
        Ok(Self { router })
    }
}

impl Lookup for MatchitArm {
    type Scratch = ();

    #[inline]
    fn lookup<'a>(&self, _scratch: &mut (), path: &'a str, caps: &mut Captures<'a>) -> Option<u32> {
        match self.router.at(path) {
            Ok(m) => {
                for (_, v) in m.params.iter() {
                    caps.push(v);
                }
                Some(*m.value)
            }
            Err(_) => None,
        }
    }
}
