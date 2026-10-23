//! The routes file and the route model, as in bench/core/route.hpp and route.cpp (render and
//! parse_route). A routes file has one route per line, `GET <pattern>`, in rbench's syntax: `{p0}`
//! is one segment and `{*p0}` is the rest of the path. Route i is line i. The routers hold these
//! routes and no other; the service answers the probe `GET /` itself (main.rs).

use std::fs;

/// kMaxParams of bench/core/route.hpp: the most captured values one route may have.
pub const MAX_PARAMS: usize = 8;

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    Literal,
    Param,
    Rest,
}

pub struct Segment {
    pub kind: Kind,
    /// The literal, or the parameter's name.
    pub text: String,
}

pub struct Route {
    pub segs: Vec<Segment>,
    /// The pattern as the file has it (rbench's syntax), for the router that takes it unconverted.
    #[cfg_attr(not(feature = "v2"), allow(dead_code))]
    pub text: String,
}

impl Route {
    /// The canonical text, `/users/{p0}/files/{*p1}` (bench/core/route.cpp, render). The root is `/`.
    pub fn render(&self) -> String {
        let mut out = String::new();
        for s in &self.segs {
            out.push('/');
            match s.kind {
                Kind::Literal => out.push_str(&s.text),
                Kind::Param => {
                    out.push('{');
                    out.push_str(&s.text);
                    out.push('}');
                }
                Kind::Rest => {
                    out.push_str("{*");
                    out.push_str(&s.text);
                    out.push('}');
                }
            }
        }
        if out.is_empty() {
            out.push('/');
        }
        out
    }
}

/// Parses canonical text (bench/core/route.cpp, parse_route). A segment `{name}` or `{*name}` is a
/// parameter; anything else is a literal. A catch-all must be the last segment.
fn parse_pattern(text: &str) -> Result<Route, String> {
    let rest = text.strip_prefix('/').ok_or_else(|| format!("route must start with '/': {text}"))?;
    let mut segs: Vec<Segment> = Vec::new();
    if rest.is_empty() {
        return Ok(Route { segs, text: text.to_string() });
    }
    for seg in rest.split('/') {
        if seg.is_empty() {
            return Err(format!("empty segment in route: {text}"));
        }
        if matches!(segs.last(), Some(Segment { kind: Kind::Rest, .. })) {
            return Err(format!("a catch-all must be the last segment: {text}"));
        }
        if seg.len() >= 3 && seg.starts_with('{') && seg.ends_with('}') {
            let rest_kind = seg.as_bytes()[1] == b'*';
            let name = &seg[if rest_kind { 2 } else { 1 }..seg.len() - 1];
            if name.is_empty() {
                return Err(format!("unnamed parameter in route: {text}"));
            }
            let kind = if rest_kind { Kind::Rest } else { Kind::Param };
            segs.push(Segment { kind, text: name.to_string() });
        } else {
            segs.push(Segment { kind: Kind::Literal, text: seg.to_string() });
        }
    }
    let params = segs.iter().filter(|s| s.kind != Kind::Literal).count();
    if params > MAX_PARAMS {
        return Err(format!("more than {MAX_PARAMS} parameters in route: {text}"));
    }
    Ok(Route { segs, text: text.to_string() })
}

/// Reads the routes file. CR before the newline is stripped and empty lines are skipped. Any other
/// line that is not `GET /...` is refused. Returns the routes in file order.
pub fn load(path: &str) -> Result<Vec<Route>, String> {
    let bytes = fs::read(path).map_err(|e| format!("cannot read {path}: {e}"))?;
    let text = String::from_utf8(bytes).map_err(|_| format!("{path} is not UTF-8"))?;
    let mut routes = Vec::new();
    for line in text.split('\n') {
        let line = line.strip_suffix('\r').unwrap_or(line);
        if line.is_empty() {
            continue;
        }
        let Some(pattern) = line.strip_prefix("GET ").filter(|p| p.starts_with('/')) else {
            return Err(format!("routes file: not \"GET <pattern>\": {line}"));
        };
        routes.push(parse_pattern(pattern)?);
    }
    Ok(routes)
}
