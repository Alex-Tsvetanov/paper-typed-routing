//! path-tree 0.8.3 as a router of the server. It follows round 2's arm: the pattern text is built
//! segment by segment (bench/arms/path_tree.cpp, `add`: `:name` for a parameter and `:name+` for a
//! catch-all of one or more segments), the build is
//! `PathTree::insert` per route (bench/arms/rust/path_tree_arm.rs, `rb_path_tree_insert`, whose
//! result is ignored because insert has no error of its own) and the lookup is `PathTree::find`
//! with the captured values taken from `raws` in pattern order (`rb_path_tree_find`). One tree:
//! the routes file is GET only. Nothing is copied: `raws` are slices of the request path.
//!
//! The root. Round 2's conversion gives a route without segments the empty pattern. Whether
//! `PathTree::insert("")` then matches `/` depends on the routes inserted before it (measured:
//! it did as the last of ten routes and did not as the second of three), and no routes file made
//! from round 2's tables has a root route. The server does not give this router the probe `/`
//! (main.rs answers it), but a routes file may have a `GET /` route of its own: this arm writes it
//! as `/`. It is the one place where the pattern text differs from what round 2's `add` would
//! produce.

use path_tree::PathTree;

use crate::routes::{Kind, Route};
use crate::{Captures, Lookup};

pub struct PathTreeArm {
    tree: PathTree<u32>,
}

impl PathTreeArm {
    /// Route i gets id i.
    pub fn build(routes: &[Route]) -> Result<Self, String> {
        let mut tree = PathTree::new();
        for (id, route) in routes.iter().enumerate() {
            let mut pattern = String::new();
            for s in &route.segs {
                pattern.push('/');
                match s.kind {
                    Kind::Literal => pattern.push_str(&s.text),
                    Kind::Param => {
                        pattern.push(':');
                        pattern.push_str(&s.text);
                    }
                    Kind::Rest => {
                        pattern.push(':');
                        pattern.push_str(&s.text);
                        pattern.push('+');
                    }
                }
            }
            if pattern.is_empty() {
                pattern.push('/');
            }
            let _ = tree.insert(&pattern, id as u32);
        }
        Ok(Self { tree })
    }
}

impl Lookup for PathTreeArm {
    type Scratch = ();

    #[inline]
    fn lookup<'a>(&self, _scratch: &mut (), path: &'a str, caps: &mut Captures<'a>) -> Option<u32> {
        match self.tree.find(path) {
            Some((value, p)) => {
                for v in p.raws.iter() {
                    caps.push(v);
                }
                Some(*value)
            }
            None => None,
        }
    }
}
