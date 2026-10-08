// Per-lookup timing with the time-stamp counter (x86-64 only; the lab host is x86-64).
// lfence before rdtsc and rdtscp then lfence after the lookup keep the lookup between the
// two reads. The empty-interval cost is measured and subtracted.
#pragma once

#include <x86intrin.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <thread>
#include <vector>

namespace rb::tsc {

inline std::uint64_t start() {
    _mm_lfence();
    const std::uint64_t t = __rdtsc();
    _mm_lfence();
    return t;
}

inline std::uint64_t stop() {
    unsigned aux = 0;
    const std::uint64_t t = __rdtscp(&aux);
    _mm_lfence();
    return t;
}

// Counter ticks per nanosecond, against steady_clock over about 200 ms.
inline double ticks_per_ns() {
    const auto c0 = std::chrono::steady_clock::now();
    const std::uint64_t t0 = start();
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    const std::uint64_t t1 = stop();
    const auto c1 = std::chrono::steady_clock::now();
    const double ns = std::chrono::duration<double, std::nano>(c1 - c0).count();
    return static_cast<double>(t1 - t0) / ns;
}

// Median ticks of an empty start()/stop() pair.
inline std::uint64_t overhead_ticks() {
    std::vector<std::uint64_t> v(1 << 16);
    for (auto& x : v) {
        const std::uint64_t a = start();
        x = stop() - a;
    }
    std::nth_element(v.begin(), v.begin() + static_cast<std::ptrdiff_t>(v.size() / 2), v.end());
    return v[v.size() / 2];
}

}  // namespace rb::tsc
