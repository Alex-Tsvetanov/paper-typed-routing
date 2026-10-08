// Heap accounting for every allocation that goes through malloc: C++ operator new, C code
// and Rust's system allocator all end there. Go's heap does not, so the Go arm reports its
// own counts from the Go runtime.
//
// Counting is on only inside a Window (the build and the allocation pass). Outside one,
// malloc and free go straight to glibc without asking the allocator for block sizes, so no
// timed loop pays for the accounting of an arm that allocates per lookup.
//
// In a plain Linux build this binary defines malloc, free and their relatives and forwards
// them to glibc's __libc_* entry points. Under a sanitizer the sanitizer owns malloc, and the
// same counters are fed from __sanitizer_install_malloc_and_free_hooks instead.
#pragma once

#include <cstddef>
#include <cstdint>

namespace rb::alloc {

struct Snapshot {
    std::uint64_t calls = 0;   // successful allocations (malloc, calloc, realloc, aligned)
    std::uint64_t bytes = 0;   // bytes allocated, by usable size, never decreasing
    std::int64_t live = 0;     // bytes allocated minus bytes freed, by usable size
};

// Counters of the calling thread. The harness is single-threaded while it measures.
Snapshot now();

// Whether counting works in this build ("interpose", "sanitizer-hooks" or "none").
const char* mechanism();

// Counting on for the calling thread while it lives; windows do not nest.
class Window {
public:
    Window();
    ~Window();
    Window(const Window&) = delete;
    Window& operator=(const Window&) = delete;
};

// While an Arena scope lives, the calling thread's malloc, calloc and aligned allocations
// come one after another from one contiguous block of `bytes` bytes (where malloc is
// interposed; elsewhere this does nothing and arena_used() says so). What is allocated there
// must never be freed: the block is the process's for good. The harness builds the timed
// loops' copy of the ring in one (core/runner.hpp).
class Arena {
public:
    explicit Arena(std::size_t bytes);
    ~Arena();
    Arena(const Arena&) = delete;
    Arena& operator=(const Arena&) = delete;
    // Whether every allocation of the scope came from the block.
    bool whole() const;
};
bool arena_used();

}  // namespace rb::alloc
