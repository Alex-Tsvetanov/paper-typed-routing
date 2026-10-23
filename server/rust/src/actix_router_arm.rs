//! actix-router 0.5.4 as a router of the server. It follows round 2's arm: the pattern text is
//! `/` + literal, `{name}` or `{name}*` per segment (bench/arms/actix_router.cpp, `add`; the root
//! route has the empty pattern), the build is `ResourceDef::new` into a `Router::build()` list in
//! registration order and `finish()` (bench/arms/rust/actix_router_arm.rs, `rb_actix_insert` and
//! `rb_actix_finalize`) and the lookup is `Router::recognize` over a `Path<&str>` (`rb_actix_at`).
//! The first route of the list that matches wins; the list is scanned linearly.
//!
//! The root. Round 2's conversion gives a route without segments the empty pattern, and
//! actix-router matches an empty pattern against the empty path only, never against `/`
//! (`ResourceDef::new("")` and the query `/` give no match; `ResourceDef::new("/")` matches `/` and
//! nothing else). No routes file made from round 2's tables has a root route, so round 2's arm
//! never met this. The server does not give this router the probe `/` (main.rs answers it), but a
//! routes file may have a `GET /` route of its own: this arm writes it as `/`. It is the one place
//! where the pattern text differs from what round 2's `add` would produce.
//!
//! Round 2 kept one `Path` in the arm and set it to each query (`Path::set` keeps the capacity of
//! its segment vector). Here each connection owns one (`Scratch`), so the router stays shared
//! read-only and a lookup does not allocate a new segment vector.
//!
//! `ResourceDef::new` panics on a pattern it cannot parse, and the crate is built with
//! panic = "abort", so `build` refuses a route the way round 2's `unparsable` does: a parameter
//! name that is not an identifier, a name repeated in the route, more than 16 parameters, or a
//! literal with '{', '}' or a trailing '*'.

use actix_router::{Path, ResourceDef, Router};

use crate::routes::{Kind, Route};
use crate::{Captures, Lookup};

/// MAX_DYNAMIC_SEGMENTS in actix-router's resource.rs.
const MAX_DYNAMIC: usize = 16;

pub struct ActixRouterArm {
    router: Router<u32>,
}

/// The query path of the last lookup. Its type says 'static; it points into the request path of one
/// lookup, and is never read after that lookup.
#[derive(Default)]
pub struct Scratch(Path<&'static str>);

fn is_identifier(s: &str) -> bool {
    !s.is_empty() && !s.as_bytes()[0].is_ascii_digit() && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
}

/// Why `ResourceDef::new` would panic on the route's pattern (bench/arms/actix_router.cpp, `unparsable`).
fn unparsable(route: &Route) -> Option<String> {
    let mut names: Vec<&str> = Vec::new();
    for (i, s) in route.segs.iter().enumerate() {
        if s.kind == Kind::Literal {
            if s.text.contains(['{', '}']) || (i + 1 == route.segs.len() && s.text.ends_with('*')) {
                return Some(format!("literal '{}' would be read as pattern syntax", s.text));
            }
            continue;
        }
        if !is_identifier(&s.text) {
            return Some(format!("parameter name '{}' is not a regex capture name", s.text));
        }
        if names.contains(&s.text.as_str()) {
            return Some(format!("parameter name '{}' repeats", s.text));
        }
        names.push(&s.text);
    }
    (names.len() > MAX_DYNAMIC).then(|| "more than 16 parameters".to_string())
}

impl ActixRouterArm {
    /// Route i gets id i.
    pub fn build(routes: &[Route]) -> Result<Self, String> {
        let mut builder = Router::build();
        for (id, route) in routes.iter().enumerate() {
            if let Some(why) = unparsable(route) {
                return Err(format!("actix-router refuses route {id}: {why}"));
            }
            let mut pattern = String::new();
            for s in &route.segs {
                pattern.push('/');
                match s.kind {
                    Kind::Literal => pattern.push_str(&s.text),
                    Kind::Param => {
                        pattern.push('{');
                        pattern.push_str(&s.text);
                        pattern.push('}');
                    }
                    Kind::Rest => {
                        pattern.push('{');
                        pattern.push_str(&s.text);
                        pattern.push_str("}*");
                    }
                }
            }
            if pattern.is_empty() {
                pattern.push('/');
            }
            builder.rdef(ResourceDef::new(pattern), id as u32);
        }
        Ok(Self { router: builder.finish() })
    }
}

impl Lookup for ActixRouterArm {
    type Scratch = Scratch;

    #[inline]
    fn lookup<'a>(&self, scratch: &mut Scratch, path: &'a str, caps: &mut Captures<'a>) -> Option<u32> {
        // SAFETY: the path outlives this call. `Path::set` is the first use of the scratch in each
        // lookup and replaces the previous request's path, so the stale reference is never read.
        let text: &'static str = unsafe { std::mem::transmute::<&'a str, &'static str>(path) };
        scratch.0.set(text);
        let (id, _) = self.router.recognize(&mut scratch.0)?;
        let id = *id;
        for (_, v) in scratch.0.iter() {
            // The captured values are slices of the path; take them back as slices of `path`.
            let start = v.as_ptr() as usize - path.as_ptr() as usize;
            caps.push(&path[start..start + v.len()]);
        }
        Some(id)
    }
}
