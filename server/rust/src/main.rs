//! The round 3 server program of the Rust routers (design/round3/end-to-end.md, sections 5 and 6):
//!
//!     mserver-rs --port P --workers 1 --routes FILE --router matchit|path-tree|actix-router|null|v2 [--check]
//!
//! hyper's HTTP/1 server on tokio's current-thread runtime, one listener on 127.0.0.1:P, one
//! worker. It is ready when the socket accepts. SIGTERM and SIGINT (Unix) or Ctrl-C and Ctrl-Break
//! (Windows) stop it with exit code 0. Exit code 2 is a refused command line or routes file, 3 is
//! a routes file a router refuses (a conflict, a pattern it cannot take), 1 is a failure at run
//! time. The first line on stderr names the instruction set the program was built for; with the
//! feature `v2` a second names the v2 library and its build information.
//!
//! Router `v2` (cargo feature `v2`) is RegexMatcher v2 behind its C interface, server/capi/p2v2.h.
//!
//! Routes: the file's `GET <pattern>` lines, route i being line i. The routers hold exactly these
//! routes, never a `/` of their own. The service answers `GET /` (and `HEAD /`) itself, before it
//! calls the router and for every router including null: route m (m is the number of routes), no
//! captured values. That is the readiness probe of lab/t1. If the file has a `GET /` route, `/` is
//! routed like any other path and there is no probe case.
//!
//! Answers (GET and HEAD):
//! - a route found (or the probe), measured mode: 200, `content-type: text/plain`, the body `Hello, World!`. The
//!   route id and every captured value (its length and first byte) are folded into a value
//!   `black_box` keeps, as round 2's timed loops do (bench/core/runner.hpp, `fold`);
//! - a route found (or the probe), `--check`: the same status and type, the body being the route id in decimal,
//!   then a tab and each captured value, then a newline;
//! - no route: 404 with an empty body.
//! Another method looks the path up as GET: a route found gives 405 with `allow: GET, HEAD`, none
//! gives 404, both with an empty body (the C++ server's rule).
//!
//! Nothing is logged per request. The runtime has an I/O driver and no time driver, and hyper is
//! given no timeout, so no timer exists. The router is built once, leaked and shared read-only; the
//! only mutable state is a scratch value each connection owns (`Lookup::Scratch`).

mod actix_router_arm;
mod matchit_arm;
mod null_arm;
mod path_tree_arm;
mod routes;
mod stop;
#[cfg(feature = "v2")]
mod v2_arm;

use std::cell::RefCell;
use std::convert::Infallible;
use std::fmt::Write as _;
use std::future::ready;
use std::hint::black_box;
use std::net::SocketAddr;
use std::process::ExitCode;

use bytes::Bytes;
use http_body_util::Full;
use hyper::body::Incoming;
use hyper::header::{HeaderValue, ALLOW, CONTENT_TYPE};
use hyper::server::conn::http1;
use hyper::service::service_fn;
use hyper::{Method, Request, Response, StatusCode};
use hyper_util::rt::TokioIo;
use tokio::net::{TcpListener, TcpStream};

use crate::actix_router_arm::ActixRouterArm;
use crate::matchit_arm::MatchitArm;
use crate::null_arm::NullArm;
use crate::path_tree_arm::PathTreeArm;
use crate::routes::MAX_PARAMS;
use crate::stop::Stop;
#[cfg(feature = "v2")]
use crate::v2_arm::V2Arm;

const BODY: &[u8] = b"Hello, World!";
const TEXT_PLAIN: HeaderValue = HeaderValue::from_static("text/plain");
const ALLOWED: HeaderValue = HeaderValue::from_static("GET, HEAD");
const USAGE: &str = "usage: mserver-rs --port P --workers 1 --routes FILE --router matchit|path-tree|actix-router|null|v2 [--check]";

/// The captured values of one lookup, in pattern order, as slices of the request path.
pub struct Captures<'a> {
    n: usize,
    v: [&'a str; MAX_PARAMS],
}

impl<'a> Captures<'a> {
    #[inline]
    fn new() -> Self {
        Self { n: 0, v: [""; MAX_PARAMS] }
    }

    /// Keeps the value; one beyond MAX_PARAMS is dropped, as in round 2's arms. The routes file
    /// is refused at start if a route could have more.
    #[inline]
    pub fn push(&mut self, value: &'a str) {
        if self.n < MAX_PARAMS {
            self.v[self.n] = value;
            self.n += 1;
        }
    }

    #[inline]
    fn values(&self) -> &[&'a str] {
        &self.v[..self.n]
    }
}

/// What the server asks of a router: the id of the route the path matches, and its captured values.
pub trait Lookup: Sync + 'static {
    /// Mutable state a connection owns and passes to every lookup on it.
    type Scratch: Default + Send + 'static;

    fn lookup<'a>(&self, scratch: &mut Self::Scratch, path: &'a str, caps: &mut Captures<'a>) -> Option<u32>;
}

/// What a timed loop keeps of one lookup: the id and every captured value (bench/core/runner.hpp, `fold`).
#[inline]
fn fold(id: u32, caps: &Captures) -> u64 {
    let mut sum = u64::from(id);
    for v in caps.values() {
        sum = sum.wrapping_add(v.len() as u64 + u64::from(v.as_bytes().first().copied().unwrap_or(0)));
    }
    sum
}

fn check_body(id: u32, caps: &Captures) -> Bytes {
    let mut s = String::with_capacity(16 + caps.values().iter().map(|v| v.len() + 1).sum::<usize>());
    let _ = write!(s, "{id}");
    for v in caps.values() {
        s.push('\t');
        s.push_str(v);
    }
    s.push('\n');
    Bytes::from(s)
}

fn reply(status: StatusCode, body: Bytes) -> Response<Full<Bytes>> {
    let mut res = Response::new(Full::new(body));
    *res.status_mut() = status;
    res
}

/// What the service needs besides the router.
#[derive(Clone, Copy)]
struct Config {
    check: bool,
    /// The route id answered for `/` without calling the router: m, the number of routes. None
    /// when the routes file has a `/` route of its own.
    probe: Option<u32>,
}

/// The whole service: answers the probe, or looks the path up, and builds the answer.
fn answer<R: Lookup>(router: &R, scratch: &mut R::Scratch, cfg: Config, req: &Request<Incoming>) -> Response<Full<Bytes>> {
    let mut caps = Captures::new();
    let path = req.uri().path();
    let found = match cfg.probe {
        Some(m) if path == "/" => Some(m),
        _ => router.lookup(scratch, path, &mut caps),
    };
    let Some(id) = found else {
        return reply(StatusCode::NOT_FOUND, Bytes::new());
    };
    if req.method() != Method::GET && req.method() != Method::HEAD {
        let mut res = reply(StatusCode::METHOD_NOT_ALLOWED, Bytes::new());
        res.headers_mut().insert(ALLOW, ALLOWED);
        return res;
    }
    let body = if cfg.check {
        check_body(id, &caps)
    } else {
        black_box(fold(id, &caps));
        Bytes::from_static(BODY)
    };
    let mut res = reply(StatusCode::OK, body);
    res.headers_mut().insert(CONTENT_TYPE, TEXT_PLAIN);
    res
}

async fn connection<R: Lookup>(stream: TcpStream, http: &'static http1::Builder, router: &'static R, cfg: Config) {
    if stream.set_nodelay(true).is_err() {
        return;
    }
    let scratch = RefCell::new(R::Scratch::default());
    let service = service_fn(move |req: Request<Incoming>| {
        ready(Ok::<_, Infallible>(answer(router, &mut scratch.borrow_mut(), cfg, &req)))
    });
    // A connection that fails or closes is the client's business: nothing is logged.
    let _ = http.serve_connection(TokioIo::new(stream), service).await;
}

/// Runs the server until a stop signal. The routers are built before the runtime starts.
fn serve<R: Lookup>(router: R, port: u16, cfg: Config) -> ExitCode {
    let router: &'static R = Box::leak(Box::new(router));
    let mut builder = http1::Builder::new();
    // Keep-alive. hyper's default header-read timeout (30 s) needs a timer; with None it makes none.
    builder.keep_alive(true).header_read_timeout(None);
    let http: &'static http1::Builder = Box::leak(Box::new(builder));

    // hyper-util's `tokio` feature turns tokio's `time` feature on, but only enable_io() is asked
    // for here: the runtime has no time driver, and a timer call would panic. hyper makes none.
    let runtime = match tokio::runtime::Builder::new_current_thread().enable_io().build() {
        Ok(rt) => rt,
        Err(e) => {
            eprintln!("mserver-rs: cannot start the runtime: {e}");
            return ExitCode::from(1);
        }
    };
    let outcome: std::io::Result<()> = runtime.block_on(async move {
        let mut stop = Stop::new()?;
        let listener = TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], port))).await?;
        loop {
            tokio::select! {
                biased;
                _ = stop.wait() => return Ok(()),
                accepted = listener.accept() => {
                    // A failed accept (a reset before it, no descriptor left) loses that connection only.
                    if let Ok((stream, _)) = accepted {
                        tokio::spawn(connection(stream, http, router, cfg));
                    }
                }
            }
        }
    });
    match outcome {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("mserver-rs: {e}");
            ExitCode::from(1)
        }
    }
}

struct Args {
    port: u16,
    routes: String,
    router: String,
    check: bool,
}

fn parse_args(mut args: impl Iterator<Item = String>) -> Result<Args, String> {
    let (mut port, mut workers, mut routes, mut router, mut check) = (None, None, None, None, false);
    while let Some(a) = args.next() {
        if a == "--check" {
            check = true;
            continue;
        }
        let slot = match a.as_str() {
            "--port" => &mut port,
            "--workers" => &mut workers,
            "--routes" => &mut routes,
            "--router" => &mut router,
            _ => return Err(format!("an unknown option: {a}")),
        };
        *slot = Some(args.next().ok_or_else(|| format!("{a} without its value"))?);
    }
    if workers.as_deref().unwrap_or("1") != "1" {
        return Err("one worker only (--workers 1)".to_string());
    }
    let (Some(port), Some(routes), Some(router)) = (port, routes, router) else {
        return Err("--port, --routes and --router are required".to_string());
    };
    let port = port.parse::<u16>().map_err(|_| format!("not a port: {port}"))?;
    Ok(Args { port, routes, router, check })
}

fn refuse(why: &str) -> ExitCode {
    eprintln!("mserver-rs: {why}\n{USAGE}");
    ExitCode::from(2)
}

/// A router refused the routes file (the C++ and Go programs use 3 for this).
fn refused_by_router(why: &str) -> ExitCode {
    eprintln!("mserver-rs: {why}");
    ExitCode::from(3)
}

fn main() -> ExitCode {
    eprintln!(
        "mserver-rs: target-cpu {}, avx2 {}",
        env!("MSERVER_TARGET_CPU"),
        if cfg!(target_feature = "avx2") { "yes" } else { "no" }
    );
    #[cfg(feature = "v2")]
    eprintln!("mserver-rs: {}", v2_arm::describe());
    let args = match parse_args(std::env::args().skip(1)) {
        Ok(a) => a,
        Err(why) => return refuse(&why),
    };
    let routes = match routes::load(&args.routes) {
        Ok(r) => r,
        Err(why) => return refuse(&why),
    };
    let has_root = routes.iter().any(|r| r.segs.is_empty());
    let cfg = Config { check: args.check, probe: if has_root { None } else { Some(routes.len() as u32) } };
    // Each router is a type, so the service is compiled once per router and calls it directly.
    match args.router.as_str() {
        "matchit" => match MatchitArm::build(&routes) {
            Ok(r) => serve(r, args.port, cfg),
            Err(why) => refused_by_router(&why),
        },
        "path-tree" => match PathTreeArm::build(&routes) {
            Ok(r) => serve(r, args.port, cfg),
            Err(why) => refused_by_router(&why),
        },
        "actix-router" => match ActixRouterArm::build(&routes) {
            Ok(r) => serve(r, args.port, cfg),
            Err(why) => refused_by_router(&why),
        },
        "null" => serve(NullArm, args.port, cfg),
        #[cfg(feature = "v2")]
        "v2" => match V2Arm::build(&routes) {
            Ok(r) => serve(r, args.port, cfg),
            Err(why) => refused_by_router(&why),
        },
        #[cfg(not(feature = "v2"))]
        "v2" => refuse("router v2 is not in this build (cargo feature v2, with P2V2_LIB_DIR set)"),
        other => refuse(&format!("an unknown router: {other}")),
    }
}
