//! Two jobs.
//! 1. It records the -C target-cpu the compiler is given, so the program can say at start which
//!    instruction set it was built for (.cargo/config.toml sets it; a build from another
//!    directory would not, and the line would then say "none").
//! 2. With the cargo feature `v2` it links the static library p2v2_c (server/capi/p2v2.h, built by
//!    the C++ server's CMake project) from the directory the environment variable P2V2_LIB_DIR
//!    names, and on Linux the C++ runtime it was built against (libstdc++). Without the variable
//!    the build fails here, with the reason.

use std::env;
use std::path::Path;
use std::process::{exit, Command};

/// The CPU `native` stands for on this host, from rustc's own listing, or None.
fn native_cpu() -> Option<String> {
    let rustc = env::var("RUSTC").ok()?;
    let out = Command::new(rustc).args(["-C", "target-cpu=native", "--print=target-cpus"]).output().ok()?;
    let text = String::from_utf8(out.stdout).ok()?;
    let rest = text.split("(currently ").nth(1)?;
    Some(rest.split(')').next()?.to_string())
}

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-env-changed=CARGO_ENCODED_RUSTFLAGS");
    let flags = env::var("CARGO_ENCODED_RUSTFLAGS").unwrap_or_default();
    let cpu = flags
        .split('\x1f')
        .filter_map(|p| p.strip_prefix("-C").unwrap_or(p).strip_prefix("target-cpu="))
        .last()
        .map(|c| {
            if c == "native" {
                native_cpu().map_or_else(|| "native".to_string(), |n| format!("native ({n})"))
            } else {
                c.to_string()
            }
        })
        .unwrap_or_else(|| "none".to_string());
    println!("cargo:rustc-env=MSERVER_TARGET_CPU={cpu}");
    if env::var_os("CARGO_FEATURE_V2").is_some() {
        link_v2();
    }
}

/// Links p2v2_c from P2V2_LIB_DIR, or ends the build with a message.
fn link_v2() {
    println!("cargo:rerun-if-env-changed=P2V2_LIB_DIR");
    let target_os = env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    let file = if target_os == "windows" { "p2v2_c.lib" } else { "libp2v2_c.a" };
    let Some(dir) = env::var_os("P2V2_LIB_DIR").filter(|d| !d.is_empty()) else {
        eprintln!("error: the cargo feature `v2` links the static library {file}, and P2V2_LIB_DIR is not set.");
        eprintln!("Set P2V2_LIB_DIR to the directory of the C++ server's build that holds it (the build of");
        eprintln!("server/capi/p2v2.cpp), or build without `--features v2`.");
        exit(1);
    };
    let path = Path::new(&dir).join(file);
    if !path.is_file() {
        eprintln!("error: P2V2_LIB_DIR is {}, and it holds no {file}.", Path::new(&dir).display());
        exit(1);
    }
    println!("cargo:rerun-if-changed={}", path.display());
    println!("cargo:rustc-link-search=native={}", Path::new(&dir).display());
    println!("cargo:rustc-link-lib=static=p2v2_c");
    if target_os == "linux" {
        println!("cargo:rustc-link-lib=stdc++");
    }
}
