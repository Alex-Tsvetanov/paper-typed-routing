#include "report.hpp"

#include <cstdio>

namespace p2gen {

namespace {

// A JSON object under construction.
class Json {
public:
    Json& num(const char* key, std::uint64_t v) { return raw(key, std::to_string(v)); }

    Json& real(const char* key, double v, int digits) {
        char buf[64];
        std::snprintf(buf, sizeof buf, "%.*f", digits, v);
        return raw(key, buf);
    }

    Json& text(const char* key, std::string_view v) {
        std::string quoted = "\"";
        for (const char c : v) {
            const auto u = static_cast<unsigned char>(c);
            if (c == '"' || c == '\\') {
                quoted += '\\';
                quoted += c;
            } else if (u < 0x20) {
                char esc[8];
                std::snprintf(esc, sizeof esc, "\\u%04x", static_cast<unsigned>(u));
                quoted += esc;
            } else {
                quoted += c;
            }
        }
        quoted += '"';
        return raw(key, quoted);
    }

    Json& raw(const char* key, const std::string& value) {
        if (!body_.empty()) {
            body_ += ',';
        }
        body_ += '"';
        body_ += key;
        body_ += "\":";
        body_ += value;
        return *this;
    }

    std::string str() const { return "{" + body_ + "}"; }

private:
    std::string body_;
};

// The counters, as fields of j.
void put_counters(Json& j, const Counters& c) {
    Json errors;
    errors.num("status", c.status)
        .num("body", c.body)
        .num("framing", c.framing)
        .num("lost", c.lost)
        .num("unsolicited", c.unsolicited);
    j.num("completed", c.completed)
        .raw("errors", errors.str())
        .num("timeouts", c.timeouts)
        .num("errors_total", c.errors())
        .num("connect_errors", c.connect_errors)
        .num("resets", c.resets)
        .num("peer_closes", c.peer_closes)
        .num("reconnects", c.reconnects);
}

std::string counters_object(const Counters& c) {
    Json j;
    put_counters(j, c);
    return j.str();
}

std::string latency_object(const Histogram& h) {
    Json j;
    j.num("count", h.count())
        .real("mean", h.mean(), 1)
        .num("min", h.min())
        .num("p50", h.quantile(0.50))
        .num("p90", h.quantile(0.90))
        .num("p99", h.quantile(0.99))
        .num("p999", h.quantile(0.999))
        .num("max", h.max());
    return j.str();
}

}  // namespace

std::string render_timed(const Options& o, std::string_view commit, std::size_t targets, std::size_t request_bytes,
                         std::uint64_t t0_ns, std::uint64_t t1_ns, const Totals& t) {
    Json j;
    j.text("tool", "p2gen")
        .text("commit", commit)
        .text("mode", "timed")
        .text("host", o.host)
        .num("port", static_cast<std::uint64_t>(o.port))
        .text("paths_file", o.paths)
        .num("targets", targets)
        .num("request_bytes", request_bytes)
        .num("threads", static_cast<std::uint64_t>(o.threads))
        .num("connections", static_cast<std::uint64_t>(o.connections))
        .real("warmup_s", o.warmup_s, 3)
        .real("duration_s", o.duration_s, 3)
        .num("timeout_ms", static_cast<std::uint64_t>(o.timeout_ms))
        .text("cpus", o.cpus_text)
        .num("t0_ns", t0_ns)
        .num("t1_ns", t1_ns)
        .num("measure_wall_ns", t1_ns >= t0_ns ? t1_ns - t0_ns : 0)
        .raw("measure", counters_object(t.measure))
        .raw("warmup", counters_object(t.warmup))
        .raw("latency_ns", latency_object(t.latency))
        .num("thread_failed", t.thread_failed ? 1 : 0);
    return j.str();
}

std::string render_count(const Options& o, std::string_view commit, const Totals& t) {
    Json j;
    j.text("tool", "p2gen")
        .text("commit", commit)
        .text("mode", "count")
        .text("host", o.host)
        .num("port", static_cast<std::uint64_t>(o.port))
        .num("count", o.count)
        .num("threads", static_cast<std::uint64_t>(o.threads))
        .num("connections", static_cast<std::uint64_t>(o.connections))
        .num("resolved", t.measure.resolved());
    put_counters(j, t.measure);
    j.num("thread_failed", t.thread_failed ? 1 : 0);
    return j.str();
}

bool count_ok(const Options& o, const Totals& t) noexcept {
    const Counters& c = t.measure;
    return !t.thread_failed && c.completed == o.count && c.resolved() == o.count && c.errors() == 0;
}

bool timed_ok(const Totals& t) noexcept {
    return !t.thread_failed;
}

}  // namespace p2gen
