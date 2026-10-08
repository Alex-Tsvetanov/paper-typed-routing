#include "core/cache_counters.hpp"

#include <linux/perf_event.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>
#include <fstream>

namespace rb::hwc {
namespace {

bool amd_family_19h() {
    std::ifstream in("/proc/cpuinfo");
    std::string line;
    bool amd = false;
    while (std::getline(in, line)) {
        if (line.rfind("vendor_id", 0) == 0) {
            amd = line.find("AuthenticAMD") != std::string::npos;
        } else if (line.rfind("cpu family", 0) == 0) {
            const std::size_t colon = line.find(':');
            return amd && colon != std::string::npos && std::stoi(line.substr(colon + 1)) == 0x19;
        }
    }
    return false;
}

int open_event(std::uint32_t type, std::uint64_t config, int group) {
    perf_event_attr a{};
    a.size = sizeof(a);
    a.type = type;
    a.config = config;
    a.disabled = group == -1 ? 1 : 0;
    a.exclude_kernel = 1;
    a.exclude_hv = 1;
    a.read_format = PERF_FORMAT_GROUP | PERF_FORMAT_TOTAL_TIME_ENABLED | PERF_FORMAT_TOTAL_TIME_RUNNING;
    return static_cast<int>(syscall(SYS_perf_event_open, &a, 0, -1, group, 0));
}

constexpr std::uint64_t kL1dReadMiss = PERF_COUNT_HW_CACHE_L1D | (PERF_COUNT_HW_CACHE_OP_READ << 8) |
                                       (static_cast<std::uint64_t>(PERF_COUNT_HW_CACHE_RESULT_MISS) << 16);

struct Ev {
    std::uint32_t type;
    std::uint64_t config;
    bool raw;
    const char* name;
};

// An AMD raw event: the event select in the low byte, the unit mask in the next.
constexpr Ev amd(std::uint64_t event, std::uint64_t umask, const char* name) {
    return {PERF_TYPE_RAW, event | (umask << 8), true, name};
}

constexpr Ev kMemory[] = {{PERF_TYPE_HW_CACHE, kL1dReadMiss, false, "l1d_misses"},
                          amd(0x64, 0x08, "l2_misses"), amd(0x45, 0xff, "dtlb_misses")};
constexpr Ev kAeLow[] = {amd(0xae, 0x01, "stall_ae_b0"), amd(0xae, 0x02, "stall_ae_b1"),
                         amd(0xae, 0x04, "stall_ae_b2"), amd(0xae, 0x08, "stall_ae_b3")};
constexpr Ev kAeHigh[] = {amd(0xae, 0x10, "stall_ae_b4"), amd(0xae, 0x20, "stall_ae_b5"),
                          amd(0xae, 0x40, "stall_ae_b6"), amd(0xae, 0x80, "stall_ae_b7")};
constexpr Ev kAfLow[] = {amd(0xaf, 0x01, "stall_af_b0"), amd(0xaf, 0x02, "stall_af_b1"),
                         amd(0xaf, 0x04, "stall_af_b2"), amd(0xaf, 0x08, "stall_af_b3")};
constexpr Ev kAfHigh[] = {amd(0xaf, 0x10, "stall_af_b4"), amd(0xaf, 0x20, "stall_af_b5"),
                          amd(0xaf, 0x40, "stall_af_b6"), amd(0xaf, 0x80, "stall_af_b7")};

struct SetEvents {
    const Ev* ev;
    int n;
};

SetEvents events_of(Set set) {
    switch (set) {
        case Set::Memory: return {kMemory, 3};
        case Set::AeLow: return {kAeLow, 4};
        case Set::AeHigh: return {kAeHigh, 4};
        case Set::AfLow: return {kAfLow, 4};
        case Set::AfHigh: return {kAfHigh, 4};
    }
    return {kMemory, 3};
}

}  // namespace

const char* events() {
    return "groups of cycles=hw:cpu-cycles and: {l1d_misses=hw-cache:l1d,read,miss, "
           "l2_misses=amd19h:event=0x64,umask=0x08, dtlb_misses=amd19h:event=0x45,umask=0xff}; "
           "{stall_ae_b0..3=amd19h:event=0xae,umask=0x01,0x02,0x04,0x08}; "
           "{stall_ae_b4..7=amd19h:event=0xae,umask=0x10,0x20,0x40,0x80}; "
           "{stall_af_b0..3=amd19h:event=0xaf,umask=0x01,0x02,0x04,0x08}; "
           "{stall_af_b4..7=amd19h:event=0xaf,umask=0x10,0x20,0x40,0x80}; user space only; "
           "each unit-mask bit counted and reported on its own, never summed";
}

const char* field(Set set, int i) {
    const SetEvents s = events_of(set);
    return i < s.n ? s.ev[i].name : "";
}

Group::Group(Set set) {
    for (int& fd : fd_) {
        fd = -1;
    }
    fd_[0] = open_event(PERF_TYPE_HARDWARE, PERF_COUNT_HW_CPU_CYCLES, -1);
    if (fd_[0] < 0) {
        error_ = std::string("perf_event_open(cycles): ") + std::strerror(errno);
        return;
    }
    n_ = 1;
    raw_ = amd_family_19h();
    const SetEvents s = events_of(set);
    want_ = 1 + s.n;
    for (int i = 0; i < s.n; ++i) {
        if (s.ev[i].raw && !raw_) {
            error_ = "raw events not opened: the CPU is not AMD family 19h";
            return;
        }
        fd_[1 + i] = open_event(s.ev[i].type, s.ev[i].config, fd_[0]);
        if (fd_[1 + i] < 0) {
            error_ = std::string("perf_event_open(") + s.ev[i].name + "): " + std::strerror(errno);
            return;
        }
        n_ = 2 + i;
    }
}

Group::~Group() {
    for (int fd : fd_) {
        if (fd >= 0) {
            close(fd);
        }
    }
}

void Group::start() {
    if (fd_[0] >= 0) {
        ioctl(fd_[0], PERF_EVENT_IOC_RESET, PERF_IOC_FLAG_GROUP);
        ioctl(fd_[0], PERF_EVENT_IOC_ENABLE, PERF_IOC_FLAG_GROUP);
    }
}

Totals Group::stop() {
    Totals t;
    t.raw = raw_;
    t.error = error_;
    if (fd_[0] < 0) {
        return t;
    }
    ioctl(fd_[0], PERF_EVENT_IOC_DISABLE, PERF_IOC_FLAG_GROUP);
    std::uint64_t buf[3 + 5] = {};
    const ssize_t got = read(fd_[0], buf, sizeof(buf));
    if (got < static_cast<ssize_t>((3 + n_) * sizeof(std::uint64_t)) || buf[0] != static_cast<std::uint64_t>(n_)) {
        t.error = "short read of the counter group";
        return t;
    }
    const std::uint64_t enabled = buf[1];
    const std::uint64_t running = buf[2];
    t.running_fraction = enabled == 0 ? 0.0 : static_cast<double>(running) / static_cast<double>(enabled);
    // A group runs whole or not at all; one that did not run the whole time shared the
    // counters with something else, and its counts are not used.
    t.ok = enabled != 0 && running == enabled && n_ == want_;
    if (!t.ok && t.error.empty()) {
        t.error = "the counter group was not scheduled for the whole count";
    }
    t.cycles = buf[3];
    for (int i = 1; i < n_; ++i) {
        t.v[i - 1] = buf[3 + i];
    }
    return t;
}

}  // namespace rb::hwc
