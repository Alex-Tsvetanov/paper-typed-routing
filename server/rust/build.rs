//! Records the -C target-cpu the compiler is given, so the program can say at start which
//! instruction set it was built for (.cargo/config.toml sets it; a build from another directory
//! would not, and the line would then say "none").

use std::env;
use std::process::Command;

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
}
