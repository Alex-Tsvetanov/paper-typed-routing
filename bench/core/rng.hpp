// Deterministic draws that give the same sequence on every standard library: SplitMix64
// and a multiply-shift range reduction. <random>'s distributions are not specified to agree
// across implementations, so they are not used for anything a table or a query depends on.
#pragma once

#include <cstdint>
#include <stdexcept>
#include <utility>
#include <vector>

namespace rb {

#if defined(__clang__)
#define RB_WRAPS __attribute__((no_sanitize("unsigned-integer-overflow")))
#else
#define RB_WRAPS
#endif

class SplitMix64 {
public:
    explicit SplitMix64(std::uint64_t seed) : state_(seed) {}

    RB_WRAPS std::uint64_t next() {
        state_ += 0x9E3779B97F4A7C15ULL;
        std::uint64_t z = state_;
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
        return z ^ (z >> 31);
    }

    // A draw in [0, n): the top 53 bits of next() times n, shifted down by 53. Exact 128-bit
    // product, so the result does not depend on the compiler.
    std::uint64_t below(std::uint64_t n) {
        if (n == 0) {
            throw std::invalid_argument("SplitMix64::below(0)");
        }
        const unsigned __int128 p = static_cast<unsigned __int128>(next() >> 11) * n;
        return static_cast<std::uint64_t>(p >> 53);
    }

private:
    std::uint64_t state_;
};

template <class T>
void shuffle(SplitMix64& rng, std::vector<T>& v) {
    for (std::size_t i = v.size(); i > 1; --i) {
        std::swap(v[i - 1], v[static_cast<std::size_t>(rng.below(i))]);
    }
}

}  // namespace rb
