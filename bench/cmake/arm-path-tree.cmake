# path-tree through the Rust arms' static library (cmake/ffi-rust.cmake, arms/rust/path_tree_arm.rs).
include(${CMAKE_CURRENT_LIST_DIR}/ffi-rust.cmake)
rb_rust_arm(path-tree arms/path_tree.cpp)
