# The Rust arms through one Rust static library built from one crate (arms/rust), with the
# versions Cargo.lock pins (--locked). Each Rust static library bundles its own standard
# library, so two usually collide in one executable: every Rust arm's adapter links this one
# library. Included by each cmake/arm-<Rust arm>.cmake; the first include defines everything.
include_guard(GLOBAL)

find_package(Threads REQUIRED)
find_program(RB_CARGO cargo REQUIRED)
find_program(RB_RUSTC rustc REQUIRED)
set(RB_RUST_CRATE "${CMAKE_CURRENT_SOURCE_DIR}/arms/rust")
# Every source of the crate. Each Rust arm's digest header covers all of them, as all of them
# are compiled into the library the arm links.
set(RB_RUST_FILES Cargo.toml Cargo.lock lib.rs matchit_arm.rs actix_router_arm.rs path_tree_arm.rs)
list(TRANSFORM RB_RUST_FILES PREPEND "${RB_RUST_CRATE}/" OUTPUT_VARIABLE _rust_deps)
set(_cargo_dir "${CMAKE_CURRENT_BINARY_DIR}/cargo")
set(_rust_lib "${_cargo_dir}/release/librb_rust_arms.a")
# The crate is compiled for the host's CPU (-C target-cpu, cmake/isa.cmake), as the C and C++
# arms are. Under AddressSanitizer the crate's code is instrumented too (-Zsanitizer=address).
# That flag is unstable; the stable rustc of the lab accepts it with RUSTC_BOOTSTRAP=1. The Rust
# standard library is the prebuilt one, neither instrumented nor built for the host's CPU.
# The digest header of each Rust arm names the instruction-set flags (RB_RUST_ISA_FLAGS), not the
# sanitizer's: a sanitizer build and the measured build must digest alike, as the C and C++ arms'
# inputs do (the sanitizer is what a record is of, not an input it matches).
set(RB_RUST_ENV "")
set(RB_RUST_ISA_FLAGS "")
if(RB_RUST_TARGET_CPU)
    set(RB_RUST_ISA_FLAGS "-C target-cpu=${RB_RUST_TARGET_CPU}")
endif()
set(_rustflags "${RB_RUST_ISA_FLAGS}")
if(RB_SANITIZER MATCHES "address")
    set(RB_RUST_ENV RUSTC_BOOTSTRAP=1)
    string(PREPEND _rustflags "-Zsanitizer=address ")
endif()
string(STRIP "${_rustflags}" RB_RUSTFLAGS)
list(APPEND RB_RUST_ENV "RUSTFLAGS=${RB_RUSTFLAGS}")
add_custom_command(OUTPUT "${_rust_lib}"
    COMMAND ${CMAKE_COMMAND} -E env "CARGO_TARGET_DIR=${_cargo_dir}" ${RB_RUST_ENV}
            "${RB_CARGO}" build --release --locked --quiet --manifest-path "${RB_RUST_CRATE}/Cargo.toml"
    DEPENDS ${_rust_deps}
    VERBATIM)
add_custom_target(rb_rust_build DEPENDS "${_rust_lib}")
add_library(rb_rust STATIC IMPORTED GLOBAL)
set_target_properties(rb_rust PROPERTIES IMPORTED_LOCATION "${_rust_lib}"
                      INTERFACE_LINK_LIBRARIES "Threads::Threads;${CMAKE_DL_LIBS};m")
add_dependencies(rb_rust rb_rust_build)
execute_process(COMMAND "${RB_CARGO}" --version OUTPUT_VARIABLE _cv OUTPUT_STRIP_TRAILING_WHITESPACE)
execute_process(COMMAND "${RB_RUSTC}" --version OUTPUT_VARIABLE _rv OUTPUT_STRIP_TRAILING_WHITESPACE)
set(RB_RUST_TOOLCHAIN "${_rv}; ${_cv}; RUSTFLAGS=${RB_RUST_ISA_FLAGS} (target CPU ${RB_ISA_RUST_CPU})")

# rb_rust_arm(name source): the arm's adapter, linked with the library, and its digest header
# <name>_sources.h (dashes as underscores) over the crate's sources and the Rust toolchain.
function(rb_rust_arm name source)
    string(REPLACE "-" "_" _id "${name}")
    set(RB_FFI_TOOLCHAIN "${RB_RUST_TOOLCHAIN}")
    rb_ffi_digest(${name} "${RB_RUST_CRATE}" ${_id}_sources.h ${RB_RUST_FILES})
    rb_arm(${name} ${source} rb_rust)
    target_include_directories(arm_${_id} PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/rb-ffi")
    add_dependencies(arm_${_id} rb_rust_build)
endfunction()
