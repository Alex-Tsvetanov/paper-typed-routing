//! The Rust arms of rbench in one static library (cmake/ffi-rust.cmake). Each Rust static
//! library bundles its own copy of the standard library, so two of them usually collide when
//! linked into one executable; every Rust router therefore lives in this crate, one module per
//! router. Each module exports its own C functions.

pub mod actix_router_arm;
pub mod matchit_arm;
pub mod path_tree_arm;
