# rust-null (design/review-runs/boundary-arms.md): an empty Rust function behind the Rust arms' C
# interface, through their static library (cmake/ffi-rust.cmake, arms/rust/rust_null_arm.rs).
include(${CMAKE_CURRENT_LIST_DIR}/ffi-rust.cmake)
rb_rust_arm(rust-null arms/rust_null.cpp)
