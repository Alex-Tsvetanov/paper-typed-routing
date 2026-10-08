# The Go arms through one Go c-archive built from one module (arms/go), with the module
# versions go.sum pins (-mod=readonly). Each c-archive carries its own Go runtime, so two
# cannot be linked into one executable: every Go arm's adapter links this one archive.
# Included by each cmake/arm-<Go arm>.cmake; the first include defines everything.
include_guard(GLOBAL)

find_package(Threads REQUIRED)
find_program(RB_GO go REQUIRED)
set(RB_GO_MODULE "${CMAKE_CURRENT_SOURCE_DIR}/arms/go")
# Every source of the module. Each Go arm's digest header covers all of them, as all of them
# are compiled into the archive the arm links.
set(RB_GO_FILES go.mod go.sum main.go httprouter.go nethttp.go gin.go chi.go
    gin/go.mod gin/rbshim.go gin/tree.go gin/internal/bytesconv/bytesconv.go
    chi/go.mod chi/rbshim.go chi/chain.go chi/chi.go chi/context.go chi/mux.go chi/tree.go)
list(TRANSFORM RB_GO_FILES PREPEND "${RB_GO_MODULE}/" OUTPUT_VARIABLE _go_deps)
set(_go_dir "${CMAKE_CURRENT_BINARY_DIR}/go")
set(_go_lib "${_go_dir}/librb_go_arms.a")
# Under AddressSanitizer the Go code is instrumented too (go build -asan): its heap accesses
# and the memory it reads across the cgo boundary are checked, in the process the C++ side
# runs under ASan. ThreadSanitizer and MemorySanitizer have no Go counterpart here.
set(RB_GO_BUILD_FLAGS "")
if(RB_SANITIZER MATCHES "address")
    set(RB_GO_BUILD_FLAGS -asan)
endif()
# The module is compiled for the host's x86-64 level (GOAMD64, cmake/isa.cmake), and the C that
# cgo compiles for its CPU (-march in CGO_CFLAGS, after Go's default -O2 -g), as the C and C++
# arms are.
set(RB_GO_CGO_CFLAGS "-O2 -g")
if(RB_MARCH)
    string(APPEND RB_GO_CGO_CFLAGS " -march=${RB_MARCH}")
endif()
add_custom_command(OUTPUT "${_go_lib}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${_go_dir}"
    COMMAND ${CMAKE_COMMAND} -E env CGO_ENABLED=1 "CC=${CMAKE_C_COMPILER}" GOFLAGS=-mod=readonly
            "GOAMD64=${RB_ISA_GOAMD64}" "CGO_CFLAGS=${RB_GO_CGO_CFLAGS}"
            "${RB_GO}" build ${RB_GO_BUILD_FLAGS} -buildmode=c-archive -trimpath -o "${_go_lib}" .
    WORKING_DIRECTORY "${RB_GO_MODULE}"
    DEPENDS ${_go_deps}
    VERBATIM)
add_custom_target(rb_go_build DEPENDS "${_go_lib}")
add_library(rb_go STATIC IMPORTED GLOBAL)
set_target_properties(rb_go PROPERTIES IMPORTED_LOCATION "${_go_lib}"
                      INTERFACE_LINK_LIBRARIES "Threads::Threads")
add_dependencies(rb_go rb_go_build)
execute_process(COMMAND "${RB_GO}" version OUTPUT_VARIABLE RB_GO_TOOLCHAIN OUTPUT_STRIP_TRAILING_WHITESPACE)
string(APPEND RB_GO_TOOLCHAIN "; GOAMD64=${RB_ISA_GOAMD64}; CGO_CFLAGS=${RB_GO_CGO_CFLAGS}")

# rb_go_arm(name source): the arm's adapter, linked with the archive, and its digest header
# <name>_sources.h (dashes as underscores) over the module's sources and the Go toolchain.
function(rb_go_arm name source)
    string(REPLACE "-" "_" _id "${name}")
    set(RB_FFI_TOOLCHAIN "${RB_GO_TOOLCHAIN}")
    rb_ffi_digest(${name} "${RB_GO_MODULE}" ${_id}_sources.h ${RB_GO_FILES})
    rb_arm(${name} ${source} rb_go)
    target_include_directories(arm_${_id} PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/rb-ffi")
    add_dependencies(arm_${_id} rb_go_build)
endfunction()
