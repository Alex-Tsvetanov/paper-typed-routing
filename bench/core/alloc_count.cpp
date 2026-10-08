#include "core/alloc_count.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>

#if defined(__has_feature)
#if __has_feature(address_sanitizer) || __has_feature(thread_sanitizer) || __has_feature(memory_sanitizer)
#define RB_SANITIZED 1
#endif
#endif
#if defined(__SANITIZE_ADDRESS__) || defined(__SANITIZE_THREAD__)
#define RB_SANITIZED 1
#endif

#if defined(RB_SANITIZED)
#include <sanitizer/allocator_interface.h>
#endif

namespace {

// Static TLS in the executable, so reading it never allocates (malloc may run before the
// thread's dynamic TLS exists).
__attribute__((tls_model("initial-exec"))) thread_local std::uint64_t t_calls = 0;
__attribute__((tls_model("initial-exec"))) thread_local std::uint64_t t_bytes = 0;
__attribute__((tls_model("initial-exec"))) thread_local std::int64_t t_live = 0;
__attribute__((tls_model("initial-exec"))) thread_local bool t_counting = false;
// The arena of an Arena scope: a bump allocator over one block, and whether an allocation of
// the scope did not fit in it.
__attribute__((tls_model("initial-exec"))) thread_local char* t_arena_next = nullptr;
__attribute__((tls_model("initial-exec"))) thread_local char* t_arena_end = nullptr;
__attribute__((tls_model("initial-exec"))) thread_local bool t_arena_overflow = false;

[[maybe_unused]] inline void* arena_take(std::size_t n, std::size_t align) {
    const auto at = (reinterpret_cast<std::uintptr_t>(t_arena_next) + align - 1) & ~(std::uintptr_t{align} - 1);
    if (at + n > reinterpret_cast<std::uintptr_t>(t_arena_end)) {
        t_arena_overflow = true;
        return nullptr;
    }
    t_arena_next = reinterpret_cast<char*>(at + n);
    return reinterpret_cast<void*>(at);
}

inline void on_alloc(std::size_t usable) {
    ++t_calls;
    t_bytes += usable;
    t_live += static_cast<std::int64_t>(usable);
}
inline void on_free(std::size_t usable) { t_live -= static_cast<std::int64_t>(usable); }

}  // namespace

#if defined(RB_SANITIZED)

namespace {
void malloc_hook(const volatile void* p, std::size_t) {
    if (t_counting) {
        on_alloc(__sanitizer_get_allocated_size(const_cast<const void*>(p)));
    }
}
void free_hook(const volatile void* p) {
    const void* q = const_cast<const void*>(p);
    if (t_counting && __sanitizer_get_ownership(q) != 0) {
        on_free(__sanitizer_get_allocated_size(q));
    }
}
struct Install {
    Install() { __sanitizer_install_malloc_and_free_hooks(malloc_hook, free_hook); }
} install;
}  // namespace

const char* rb::alloc::mechanism() { return "sanitizer-hooks"; }

#elif defined(__linux__) && defined(__GLIBC__)

extern "C" {
void* __libc_malloc(std::size_t);
void __libc_free(void*);
void* __libc_calloc(std::size_t, std::size_t);
void* __libc_realloc(void*, std::size_t);
void* __libc_memalign(std::size_t, std::size_t);
std::size_t malloc_usable_size(void*);

void* malloc(std::size_t n) {
    if (!t_counting) {
        if (t_arena_next != nullptr) [[unlikely]] {
            if (void* p = arena_take(n, 16)) {
                return p;
            }
        }
        return __libc_malloc(n);
    }
    void* p = __libc_malloc(n);
    if (p != nullptr) {
        on_alloc(malloc_usable_size(p));
    }
    return p;
}

void free(void* p) {
    if (t_counting && p != nullptr) {
        on_free(malloc_usable_size(p));
    }
    __libc_free(p);
}

void* calloc(std::size_t n, std::size_t size) {
    if (!t_counting) {
        if (t_arena_next != nullptr && size != 0 && n <= SIZE_MAX / size) [[unlikely]] {
            if (void* p = arena_take(n * size, 16)) {
                std::memset(p, 0, n * size);
                return p;
            }
        }
        return __libc_calloc(n, size);
    }
    void* p = __libc_calloc(n, size);
    if (p != nullptr) {
        on_alloc(malloc_usable_size(p));
    }
    return p;
}

void* realloc(void* old, std::size_t n) {
    if (!t_counting) {
        return __libc_realloc(old, n);
    }
    const std::size_t before = old != nullptr ? malloc_usable_size(old) : 0;
    void* p = __libc_realloc(old, n);
    if (p != nullptr) {
        on_free(before);
        on_alloc(malloc_usable_size(p));
    } else if (n == 0 && old != nullptr) {
        on_free(before);
    }
    return p;
}

void* memalign(std::size_t align, std::size_t n) {
    if (!t_counting) {
        if (t_arena_next != nullptr && align != 0 && (align & (align - 1)) == 0) [[unlikely]] {
            if (void* p = arena_take(n, align < 16 ? 16 : align)) {
                return p;
            }
        }
        return __libc_memalign(align, n);
    }
    void* p = __libc_memalign(align, n);
    if (p != nullptr) {
        on_alloc(malloc_usable_size(p));
    }
    return p;
}

void* aligned_alloc(std::size_t align, std::size_t n) { return memalign(align, n); }

int posix_memalign(void** out, std::size_t align, std::size_t n) {
    if (align < sizeof(void*) || (align & (align - 1)) != 0) {
        return 22;  // EINVAL
    }
    void* p = memalign(align, n);
    if (p == nullptr) {
        return 12;  // ENOMEM
    }
    *out = p;
    return 0;
}

void* valloc(std::size_t n) { return memalign(4096, n); }
}  // extern "C"

const char* rb::alloc::mechanism() { return "interpose"; }

rb::alloc::Arena::Arena(std::size_t bytes) {
    char* block = static_cast<char*>(__libc_malloc(bytes));  // for good: never freed
    t_arena_overflow = block == nullptr;
    t_arena_next = block;
    t_arena_end = block == nullptr ? nullptr : block + bytes;
}
rb::alloc::Arena::~Arena() {
    t_arena_next = nullptr;
    t_arena_end = nullptr;
}
bool rb::alloc::Arena::whole() const { return !t_arena_overflow; }
bool rb::alloc::arena_used() { return true; }

#else

const char* rb::alloc::mechanism() { return "none"; }

#endif

#if !(defined(__linux__) && defined(__GLIBC__)) || defined(RB_SANITIZED)
rb::alloc::Arena::Arena(std::size_t) {}
rb::alloc::Arena::~Arena() = default;
bool rb::alloc::Arena::whole() const { return false; }
bool rb::alloc::arena_used() { return false; }
#endif

rb::alloc::Snapshot rb::alloc::now() { return {t_calls, t_bytes, t_live}; }

rb::alloc::Window::Window() { t_counting = true; }
rb::alloc::Window::~Window() { t_counting = false; }
