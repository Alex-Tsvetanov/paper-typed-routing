# matchit through the Rust arms' static library (cmake/ffi-rust.cmake, arms/rust/matchit_arm.rs).
include(${CMAKE_CURRENT_LIST_DIR}/ffi-rust.cmake)
rb_rust_arm(matchit arms/matchit.cpp)
