// The latency histogram of p2gen. Log-linear, in the layout of lab/t1's t1gen so the two tools
// bucket alike: exact below 256 ns, then 128 sub-buckets per power of two, so every recorded value
// is within 0.4 percent of the bucket midpoint reported for it. Pure code: no clock, no I/O.
#pragma once

#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>

namespace p2gen {

class Histogram {
public:
    static constexpr int kSubBits = 7;
    static constexpr int kSub = 1 << kSubBits;
    static constexpr int kBuckets = 2 * kSub + 56 * kSub;

    // The bucket of a value, and the midpoint reported for a bucket.
    static int index(std::uint64_t v) noexcept {
        if (v < 2 * kSub) {
            return static_cast<int>(v);
        }
        const int msb = static_cast<int>(std::bit_width(v)) - 1;
        const int shift = msb - kSubBits;
        const std::uint64_t top = v >> shift;
        return 2 * kSub + (msb - (kSubBits + 1)) * kSub + static_cast<int>(top - kSub);
    }

    static std::uint64_t value(int idx) noexcept {
        if (idx < 2 * kSub) {
            return static_cast<std::uint64_t>(idx);
        }
        const int k = idx - 2 * kSub;
        const int msb = k / kSub + kSubBits + 1;
        const std::uint64_t top = static_cast<std::uint64_t>(k % kSub + kSub);
        const int shift = msb - kSubBits;
        return (top << shift) + ((std::uint64_t{1} << shift) >> 1);
    }

    void add(std::uint64_t v) noexcept {
        ++counts_[static_cast<std::size_t>(index(v))];
        if (n_ == 0 || v < min_) {
            min_ = v;
        }
        if (v > max_) {
            max_ = v;
        }
        ++n_;
        sum_ += v;
    }

    void merge(const Histogram& o) noexcept {
        for (std::size_t i = 0; i < counts_.size(); ++i) {
            counts_[i] += o.counts_[i];
        }
        if (o.n_ != 0) {
            if (n_ == 0 || o.min_ < min_) {
                min_ = o.min_;
            }
            if (o.max_ > max_) {
                max_ = o.max_;
            }
        }
        n_ += o.n_;
        sum_ += o.sum_;
    }

    // The value below which a fraction q of the samples fall: the midpoint of the bucket that holds
    // the ceil(q * n)-th sample, kept within [min, max]. 0 for an empty histogram.
    std::uint64_t quantile(double q) const noexcept {
        if (n_ == 0) {
            return 0;
        }
        const double want = q * static_cast<double>(n_);
        std::uint64_t target = static_cast<std::uint64_t>(want);
        if (static_cast<double>(target) < want) {
            ++target;
        }
        if (target == 0) {
            target = 1;
        }
        std::uint64_t acc = 0;
        for (std::size_t i = 0; i < counts_.size(); ++i) {
            acc += counts_[i];
            if (acc >= target) {
                const std::uint64_t v = value(static_cast<int>(i));
                return v > max_ ? max_ : (v < min_ ? min_ : v);
            }
        }
        return max_;
    }

    std::uint64_t count() const noexcept { return n_; }
    std::uint64_t min() const noexcept { return n_ != 0 ? min_ : 0; }
    std::uint64_t max() const noexcept { return max_; }
    double mean() const noexcept { return n_ != 0 ? static_cast<double>(sum_) / static_cast<double>(n_) : 0.0; }

private:
    std::array<std::uint64_t, static_cast<std::size_t>(kBuckets)> counts_{};
    std::uint64_t n_ = 0;
    std::uint64_t sum_ = 0;
    std::uint64_t min_ = 0;
    std::uint64_t max_ = 0;
};

}  // namespace p2gen
