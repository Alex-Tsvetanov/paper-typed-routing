# actix-router through the Rust arms' static library (cmake/ffi-rust.cmake,
# arms/rust/actix_router_arm.rs), at the version Cargo.lock pins.
include(${CMAKE_CURRENT_LIST_DIR}/ffi-rust.cmake)
rb_rust_arm(actix-router arms/actix_router.cpp)
