// How p2gen reads one HTTP/1.1 answer. Pure code: it is fed bytes, in any chunking, and says when
// an answer ends and what it was. Nothing is buffered but the head (at most kHeaderLimit bytes);
// the body is compared with the expected 13 bytes as it arrives.
//
//   - The head is the status line and the header lines up to the empty line. The status line is
//     HTTP/1.x SSS. The names Content-Length, Transfer-Encoding and Connection are matched without
//     regard to case (hyper writes them in lower case).
//   - The body is Content-Length bytes. An answer with no Content-Length is framed only for the
//     statuses 1xx, 204 and 304, which have no body. Transfer-Encoding is not expected from any
//     server of the study, so it is a framing fault, as is a head that does not parse.
//   - Connection: close is reported; the caller closes after the answer.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace p2gen {

// The body every measured answer carries.
inline constexpr std::string_view kBody = "Hello, World!";

// The most bytes a head may take before it is called a framing fault.
inline constexpr std::size_t kHeaderLimit = 16384;

struct Answer {
    int status = 0;
    std::uint64_t length = 0;  // Content-Length
    bool body_ok = false;      // the body is exactly kBody (known when the answer is Done)
    bool close = false;        // the server said Connection: close
};

class Framer {
public:
    enum class State : std::uint8_t {
        Head,  // reading the head
        Body,  // reading the body
        Done,  // one whole answer has been read
        Bad    // the bytes cannot be framed: fault() says why
    };

    // Consumes bytes of the current answer and returns how many it took. It takes all of [p, p + n)
    // unless the answer ends (Done) or cannot be framed (Bad) inside it; bytes after that are left
    // to the caller. Takes nothing once Done or Bad.
    std::size_t feed(const char* p, std::size_t n);

    State state() const noexcept { return state_; }
    const Answer& answer() const noexcept { return answer_; }
    const char* fault() const noexcept { return fault_; }

    // Ready for the next answer.
    void reset() noexcept;

private:
    std::size_t feed_head(const char* p, std::size_t n);
    std::size_t feed_body(const char* p, std::size_t n);
    void end_of_head(std::string_view head);
    bool parse_head(std::string_view head, Answer& out);
    void set_fault(const char* why) noexcept;

    State state_ = State::Head;
    Answer answer_{};
    std::string head_;           // head bytes held across reads
    std::uint64_t seen_ = 0;     // body bytes read
    bool match_ = false;         // the body bytes so far equal kBody's
    const char* fault_ = nullptr;
};

}  // namespace p2gen
