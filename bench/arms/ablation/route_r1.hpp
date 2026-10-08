#pragma once

// The exploratory ablation arm's copy of the route matcher (regexmatcher-v2-r1): RegexMatcher v2 at
// step E1 (RegexMatcher commit 00a2053, include/matcher/route.hpp), the round-1 header renamed and
// not re-engineered, here under the namespace matcher::route_r1 and the macro prefix
// MATCHER_ROUTE_R1_ so that it links beside v2 in one binary. Generated from the round-1 header;
// no other change. It shows what round 2's engineering contributed.
//
// RegexMatcher's route matcher: route patterns, a flat routing table, and the lookup over it.
//
// Everything here is constexpr, so one table layout and one lookup function serve both a
// table built at run time (routes added one by one, then frozen) and a table built at
// compile time (a constexpr object from a fixed list of routes).
//
// Path semantics (docs/route-semantics.md):
//   - bytes are compared and captured as sent; nothing is percent-decoded;
//   - a parameter matches one non-empty segment, any bytes except '/';
//   - a catch-all matches a non-empty remainder of the path, taken as sent;
//   - a trailing slash is strict;
//   - at every segment a literal beats a typed parameter, which beats a plain parameter,
//     which beats a catch-all, whatever the order of registration;
//   - a path that no route of the request's method matches, but a route of another method
//     does, is "method not allowed" (405); otherwise "not found" (404).
//
// Layout: a method whose routes are all literal is answered by one exact-match hash table keyed
// by method and whole path. Every other method has a segment trie, one root per method,
// flattened into contiguous arrays; its literal routes live in the trie too.

#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <new>
#include <span>
#include <string>
#include <string_view>
#include <vector>

// The lookup's helpers are inlined into the walk: a call per segment costs more than the
// work it does on short segments.
#if defined(_MSC_VER) && !defined(__clang__)
#define MATCHER_ROUTE_R1_INLINE [[msvc::forceinline]]
#define MATCHER_ROUTE_R1_NOINLINE [[msvc::noinline]]
#else
#define MATCHER_ROUTE_R1_INLINE [[gnu::always_inline]]
#define MATCHER_ROUTE_R1_NOINLINE [[gnu::noinline]]
#endif

namespace matcher::route_r1
{

	inline constexpr std::size_t kMaxSegments = 32;
	inline constexpr std::size_t kMaxParams = 16;
	inline constexpr std::size_t kMethodSlots = 9;  // GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS, CONNECT, TRACE
	inline constexpr std::uint32_t kNone = 0xFFFF'FFFFu;

	// ========================================================================
	// Patterns
	// ========================================================================

	enum class SegKind : std::uint8_t
	{
		Literal,
		Typed,
		Param,
		Rest
	};

	enum class ParamType : std::uint8_t
	{
		String,
		U64,
		I64
	};

	enum class PatternError : std::uint8_t
	{
		None,
		NoLeadingSlash,
		EmptySegment,
		UnclosedBrace,
		BraceInLiteral,
		EmptyName,
		BadName,
		RepeatedName,
		UnknownType,
		RestNotLast,
		NotPchar,
		TooManySegments,
		TooManyParams,
	};

	constexpr const char* describe(PatternError e) noexcept
	{
		switch (e)
		{
			case PatternError::None: return "no error";
			case PatternError::NoLeadingSlash: return "a route pattern must start with '/'";
			case PatternError::EmptySegment: return "a route pattern has an empty segment";
			case PatternError::UnclosedBrace: return "a route parameter has no closing '}'";
			case PatternError::BraceInLiteral: return "a '{' or '}' inside a literal segment";
			case PatternError::EmptyName: return "a route parameter has an empty name";
			case PatternError::BadName: return "a route parameter name is not [A-Za-z_][A-Za-z0-9_]*";
			case PatternError::RepeatedName: return "a route parameter name is repeated";
			case PatternError::UnknownType: return "a route parameter has an unknown type (string, u64, i64)";
			case PatternError::RestNotLast: return "a catch-all {*name} must be the last segment";
			case PatternError::NotPchar: return "a literal segment has a byte that is not an RFC 3986 pchar";
			case PatternError::TooManySegments: return "a route pattern has more than 32 segments";
			case PatternError::TooManyParams: return "a route pattern has more than 16 parameters";
		}
		return "unknown error";
	}

	struct Segment
	{
		SegKind kind = SegKind::Literal;
		ParamType type = ParamType::String;
		std::string_view text;  // the literal bytes, or the parameter's name
	};

	struct Pattern
	{
		std::array<Segment, kMaxSegments> segs{};
		std::uint8_t n = 0;       // segments; "/" has none
		std::uint8_t params = 0;  // typed, plain and catch-all segments
		PatternError error = PatternError::None;
		std::size_t error_offset = 0;

		constexpr bool ok() const noexcept { return error == PatternError::None; }
		constexpr bool literal() const noexcept { return params == 0; }
		constexpr ParamType param_type(std::size_t i) const noexcept
		{
			for (std::size_t s = 0, k = 0; s < n; ++s)
			{
				if (segs[s].kind != SegKind::Literal && k++ == i)
				{
					return segs[s].type;
				}
			}
			return ParamType::String;
		}
	};

	namespace detail
	{
		constexpr bool is_alpha(char c) noexcept { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }
		constexpr bool is_digit(char c) noexcept { return c >= '0' && c <= '9'; }
		constexpr bool is_hex(char c) noexcept
		{
			return is_digit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
		}

		// RFC 3986 pchar, less pct-encoded (checked by the caller).
		constexpr bool is_pchar(char c) noexcept
		{
			if (is_alpha(c) || is_digit(c))
			{
				return true;
			}
			switch (c)
			{
				case '-': case '.': case '_': case '~':                       // unreserved
				case '!': case '$': case '&': case '\'': case '(': case ')':  // sub-delims
				case '*': case '+': case ',': case ';': case '=':
				case ':': case '@':
					return true;
				default:
					return false;
			}
		}

		constexpr bool valid_name(std::string_view s) noexcept
		{
			if (s.empty() || !(is_alpha(s[0]) || s[0] == '_'))
			{
				return false;
			}
			for (char c : s)
			{
				if (!(is_alpha(c) || is_digit(c) || c == '_'))
				{
					return false;
				}
			}
			return true;
		}
	}  // namespace detail

	// Parses "/users/{id:u64}/files/{*path}". Never throws; the result names the first error
	// and the byte offset at which the text stopped being well formed.
	constexpr Pattern parse_pattern(std::string_view text) noexcept
	{
		Pattern p;
		auto fail = [&p](PatternError e, std::size_t at) {
			p.error = e;
			p.error_offset = at;
			return p;
		};
		if (text.empty() || text[0] != '/')
		{
			return fail(PatternError::NoLeadingSlash, 0);
		}
		if (text.size() == 1)
		{
			return p;  // the root
		}
		std::size_t pos = 1;
		while (true)
		{
			std::size_t end = text.find('/', pos);
			if (end == std::string_view::npos)
			{
				end = text.size();
			}
			const std::string_view seg = text.substr(pos, end - pos);
			const bool last = end == text.size();
			if (p.n > 0 && p.segs[p.n - 1].kind == SegKind::Rest)
			{
				return fail(PatternError::RestNotLast, pos);
			}
			if (seg.empty() && !last)
			{
				return fail(PatternError::EmptySegment, pos);
			}
			if (p.n == kMaxSegments)
			{
				return fail(PatternError::TooManySegments, pos);
			}
			Segment s;
			if (!seg.empty() && seg[0] == '{')
			{
				if (seg.back() != '}')
				{
					return fail(PatternError::UnclosedBrace, pos);
				}
				std::string_view inner = seg.substr(1, seg.size() - 2);
				if (inner.find_first_of("{}") != std::string_view::npos)
				{
					return fail(PatternError::BraceInLiteral, pos);
				}
				s.kind = SegKind::Param;
				if (!inner.empty() && inner[0] == '*')
				{
					s.kind = SegKind::Rest;
					inner.remove_prefix(1);
				}
				const std::size_t colon = inner.find(':');
				std::string_view name = inner.substr(0, colon);
				if (colon != std::string_view::npos)
				{
					const std::string_view type = inner.substr(colon + 1);
					if (s.kind == SegKind::Rest)
					{
						return fail(PatternError::UnknownType, pos);
					}
					if (type == "u64")
					{
						s.kind = SegKind::Typed;
						s.type = ParamType::U64;
					}
					else if (type == "i64")
					{
						s.kind = SegKind::Typed;
						s.type = ParamType::I64;
					}
					else if (type != "string")
					{
						return fail(PatternError::UnknownType, pos);
					}
				}
				if (name.empty())
				{
					return fail(PatternError::EmptyName, pos);
				}
				if (!detail::valid_name(name))
				{
					return fail(PatternError::BadName, pos);
				}
				for (std::size_t i = 0; i < p.n; ++i)
				{
					if (p.segs[i].kind != SegKind::Literal && p.segs[i].text == name)
					{
						return fail(PatternError::RepeatedName, pos);
					}
				}
				if (p.params == kMaxParams)
				{
					return fail(PatternError::TooManyParams, pos);
				}
				s.text = name;
				++p.params;
			}
			else
			{
				for (std::size_t i = 0; i < seg.size(); ++i)
				{
					const char c = seg[i];
					if (c == '{' || c == '}')
					{
						return fail(PatternError::BraceInLiteral, pos + i);
					}
					if (c == '%')
					{
						if (i + 2 >= seg.size() || !detail::is_hex(seg[i + 1]) || !detail::is_hex(seg[i + 2]))
						{
							return fail(PatternError::NotPchar, pos + i);
						}
						i += 2;
						continue;
					}
					if (!detail::is_pchar(c))
					{
						return fail(PatternError::NotPchar, pos + i);
					}
				}
				s.text = seg;
			}
			p.segs[p.n++] = s;
			if (last)
			{
				break;
			}
			pos = end + 1;
		}
		return p;
	}

	// ========================================================================
	// Typed segments
	// ========================================================================

	constexpr bool matches_u64(std::string_view s) noexcept
	{
		if (s.empty() || s.size() > 20)
		{
			return false;
		}
		for (char c : s)
		{
			if (!detail::is_digit(c))
			{
				return false;
			}
		}
		return s.size() < 20 || s <= std::string_view("18446744073709551615");
	}

	constexpr bool matches_i64(std::string_view s) noexcept
	{
		const bool neg = !s.empty() && s[0] == '-';
		const std::string_view d = neg ? s.substr(1) : s;
		if (d.empty() || d.size() > 19)
		{
			return false;
		}
		for (char c : d)
		{
			if (!detail::is_digit(c))
			{
				return false;
			}
		}
		return d.size() < 19 || d <= std::string_view(neg ? "9223372036854775808" : "9223372036854775807");
	}

	// ========================================================================
	// Bytes, words and hashes (the same results in constant evaluation and at run time)
	// ========================================================================

	namespace detail
	{
		inline constexpr std::uint64_t kSlashes = 0x2F2F'2F2F'2F2F'2F2FULL;
		inline constexpr std::uint64_t kLow = 0x0101'0101'0101'0101ULL;
		inline constexpr std::uint64_t kHigh = 0x8080'8080'8080'8080ULL;

		// Up to 8 bytes of s from pos, little-endian, zero-padded; never reads outside s.
		// At run time one 8-byte load: at pos when 8 bytes remain, otherwise the last 8 bytes
		// of s shifted down, so a copy of variable length is never needed.
		constexpr std::uint64_t load_at(std::string_view s, std::size_t pos) noexcept
		{
			const std::size_t rem = s.size() - pos;
			if (rem == 0)
			{
				return 0;
			}
			if !consteval
			{
				if constexpr (std::endian::native == std::endian::little)
				{
					std::uint64_t w;
					if (rem >= 8)
					{
						std::memcpy(&w, s.data() + pos, 8);
						return w;
					}
					if (s.size() >= 8)
					{
						std::memcpy(&w, s.data() + s.size() - 8, 8);
						return w >> (8 * (8 - rem));
					}
				}
			}
			const std::size_t n = rem < 8 ? rem : 8;
			std::uint64_t w = 0;
			for (std::size_t i = 0; i < n; ++i)
			{
				w |= static_cast<std::uint64_t>(static_cast<unsigned char>(s[pos + i])) << (8 * i);
			}
			return w;
		}

		// Whether a and b, both n bytes long, have the same bytes from index `from` on (the
		// bytes before it are known to be equal). At run time, for n >= 8, whole 8-byte words
		// and one last word that ends at n and may overlap the one before: no call, no byte
		// loop.
		MATCHER_ROUTE_R1_INLINE constexpr bool same_from(const char* a, const char* b, std::size_t n,
		                                                std::size_t from) noexcept
		{
			if !consteval
			{
				if (n >= 8)
				{
					const auto word = [](const char* p) {
						std::uint64_t w;
						std::memcpy(&w, p, 8);
						return w;
					};
					for (std::size_t i = from; i + 8 < n; i += 8)
					{
						if (word(a + i) != word(b + i))
						{
							return false;
						}
					}
					return word(a + n - 8) == word(b + n - 8);
				}
			}
			const std::string_view x(a, n);
			const std::string_view y(b, n);
			for (std::size_t i = from; i < n; i += 8)
			{
				if (load_at(x, i) != load_at(y, i))
				{
					return false;
				}
			}
			return true;
		}

		// The index of the first '/' among the first n (at most 8) bytes of w, or 8.
		constexpr std::size_t first_slash(std::uint64_t w, std::size_t n) noexcept
		{
			const std::uint64_t x = w ^ kSlashes;
			const std::uint64_t z = (x - kLow) & ~x & kHigh;
			const std::size_t i = z ? static_cast<std::size_t>(std::countr_zero(z)) / 8 : 8;
			return i < n ? i : 8;
		}

		constexpr std::uint64_t mask_low(std::size_t bytes) noexcept
		{
			return bytes >= 8 ? ~0ULL : ((1ULL << (8 * bytes)) - 1);
		}

		constexpr std::uint64_t mix(std::uint64_t h) noexcept
		{
			h ^= h >> 32;
			h *= 0xD6E8'FEB8'6659'FD93ULL;
			h ^= h >> 32;
			return h;
		}

		// A hash of a whole path and a method, read in 8-byte words.
		constexpr std::uint64_t path_hash(std::string_view s, unsigned method) noexcept
		{
			std::uint64_t h = 0x9E37'79B9'7F4A'7C15ULL ^ (static_cast<std::uint64_t>(method) << 56) ^ s.size();
			std::size_t i = 0;
			for (; i + 8 <= s.size(); i += 8)
			{
				h = (h ^ load_at(s, i)) * 0x9E37'79B9'7F4A'7C15ULL;
				h ^= h >> 29;
			}
			if (i < s.size())
			{
				h = (h ^ load_at(s, i)) * 0x9E37'79B9'7F4A'7C15ULL;
			}
			return mix(h);
		}

		// The slot hash of a literal edge: its length, its first word and its last word.
		constexpr std::uint64_t edge_hash(std::uint64_t first, std::string_view s) noexcept
		{
			std::uint64_t h = first * 0x9E37'79B9'7F4A'7C15ULL ^ s.size();
			if (s.size() > 8)
			{
				h ^= load_at(s, s.size() - 8) * 0xC2B2'AE3D'27D4'EB4FULL;
			}
			return mix(h);
		}
	}  // namespace detail

	// ========================================================================
	// The flat table
	// ========================================================================

	struct Edge
	{
		std::uint64_t word = 0;      // the first 8 bytes of the label, zero-padded
		std::uint32_t child = kNone;  // kNone marks an empty slot of a hashed node
		std::uint32_t off = 0;       // the label in the arena
		std::uint32_t len = 0;
	};

	struct Node
	{
		std::uint32_t edges = 0;  // first edge (linear) or first slot (hashed)
		std::uint32_t count = 0;  // edges (linear) or slots, a power of two (hashed)
		std::uint8_t hashed = 0;
		std::uint8_t branches = 0;  // how many kinds of child: a lookup backtracks only if > 1
		std::uint16_t pad = 0;
		std::uint32_t u64 = kNone;
		std::uint32_t i64 = kNone;
		std::uint32_t param = kNone;
		std::uint32_t rest = kNone;
		std::uint32_t route = kNone;
	};

	struct LiteralSlot
	{
		std::uint64_t hash = 0;
		std::uint32_t off = 0;
		std::uint32_t len = 0;
		std::uint32_t route = kNone;  // kNone marks an empty slot
		std::uint32_t method = 0;
	};

	constexpr std::array<std::uint32_t, kMethodSlots> no_roots() noexcept
	{
		std::array<std::uint32_t, kMethodSlots> r{};
		r.fill(kNone);
		return r;
	}

	struct TableView
	{
		std::span<const Node> nodes;
		std::span<const Edge> edges;
		std::span<const LiteralSlot> literals;  // empty, or a power of two
		std::string_view arena;
		std::array<std::uint32_t, kMethodSlots> roots = no_roots();  // kNone: no trie for the method
		std::uint16_t methods = 0;                        // bit m: some route has method m
		std::uint16_t literal_methods = 0;                // bit m: some literal route has method m
	};

	enum class Status : std::uint8_t
	{
		Found,
		MethodNotAllowed,
		NotFound
	};

	// A captured value: a view into the path the lookup was given. Trivial on purpose, so
	// that the captures of a lookup are never zeroed at run time; only the first `count`
	// of them are ever set or read.
	struct Capture
	{
		const char* ptr;
		std::size_t len;

		constexpr std::string_view view() const noexcept { return {ptr, len}; }
		constexpr operator std::string_view() const noexcept { return view(); }
		constexpr const char* data() const noexcept { return ptr; }
		constexpr std::size_t size() const noexcept { return len; }
		constexpr bool empty() const noexcept { return len == 0; }
		friend constexpr bool operator==(const Capture& a, std::string_view b) noexcept { return a.view() == b; }
	};

	struct Match
	{
		Status status = Status::NotFound;
		std::uint8_t count = 0;     // captured values
		std::uint16_t allowed = 0;  // with MethodNotAllowed: bit m set for every method that matches
		std::uint32_t route = kNone;
		std::array<Capture, kMaxParams> params;

		constexpr Match() noexcept
		{
			if consteval
			{
				params.fill(Capture{nullptr, 0});
			}
		}

		constexpr explicit operator bool() const noexcept { return status == Status::Found; }
		constexpr std::span<const Capture> values() const noexcept { return {params.data(), count}; }
	};

	namespace detail
	{
		MATCHER_ROUTE_R1_INLINE constexpr std::uint32_t find_literal(const TableView& t, unsigned method,
		                                                            std::string_view path) noexcept
		{
			if (t.literals.empty() || !(t.literal_methods & (1u << method)))
			{
				return kNone;
			}
			const std::uint64_t h = path_hash(path, method);
			const std::size_t mask = t.literals.size() - 1;
			for (std::size_t i = static_cast<std::size_t>(h) & mask;; i = (i + 1) & mask)
			{
				const LiteralSlot& s = t.literals[i];
				if (s.route == kNone)
				{
					return kNone;
				}
				if (s.hash == h && s.method == method && s.len == path.size() &&
				    same_from(t.arena.data() + s.off, path.data(), s.len, 0))
				{
					return s.route;
				}
			}
		}

		MATCHER_ROUTE_R1_INLINE constexpr std::uint32_t find_edge(const TableView& t, const Node& n, std::string_view seg,
		                                                         std::uint64_t word) noexcept
		{
			const auto matches = [&](const Edge& e) {
				return e.word == word && e.len == seg.size() &&
				       (seg.size() <= 8 || same_from(t.arena.data() + e.off, seg.data(), seg.size(), 8));
			};
			if (!n.hashed)
			{
				for (std::uint32_t i = n.edges, end = n.edges + n.count; i < end; ++i)
				{
					if (matches(t.edges[i]))
					{
						return t.edges[i].child;
					}
				}
				return kNone;
			}
			const std::size_t mask = n.count - 1;
			for (std::size_t i = static_cast<std::size_t>(edge_hash(word, seg)) & mask;; i = (i + 1) & mask)
			{
				const Edge& e = t.edges[n.edges + i];
				if (e.child == kNone)
				{
					return kNone;
				}
				if (matches(e))
				{
					return e.child;
				}
			}
		}

		struct Choice
		{
			std::uint32_t node;
			std::uint32_t pos;
			std::uint8_t n;
			std::uint8_t stage;
		};

		// The trie walk for one method. pos is the index of the next segment's first byte, or
		// path.size() + 1 once every segment is consumed.
		constexpr std::uint32_t walk(const TableView& t, std::uint32_t root, std::string_view path,
		                             std::array<Capture, kMaxParams>& values, std::uint8_t& nvalues) noexcept
		{
			std::array<Choice, kMaxSegments + 1> stack;  // trivial: never zeroed, only pushed and popped
			std::size_t sp = 0;
			std::uint32_t node = root;
			std::size_t pos = path.size() == 1 ? 2 : 1;
			std::uint8_t nv = 0;
			std::uint8_t stage = 0;
			const std::size_t len = path.size();
			while (true)
			{
				const Node& n = t.nodes[node];
				if (pos > len)
				{
					if (stage == 0 && n.route != kNone)
					{
						nvalues = nv;
						return n.route;
					}
				}
				else
				{
					// The segment at pos: its first word, and the next '/'.
					const std::size_t rem = len - pos;
					const std::uint64_t first = load_at(path, pos);
					std::size_t seglen = first_slash(first, rem);
					if (seglen == 8)
					{
						// No '/' in the first word: read on a word at a time (no call to memchr).
						seglen = rem < 8 ? rem : 8;
						while (seglen < rem)
						{
							const std::size_t k = first_slash(load_at(path, pos + seglen), rem - seglen);
							if (k < 8)
							{
								seglen += k;
								break;
							}
							seglen = seglen + 8 < rem ? seglen + 8 : rem;
						}
					}
					const std::string_view seg(path.data() + pos, seglen);  // in range: no check
					const std::uint64_t word = first & mask_low(seglen);
					const std::size_t next = pos + seglen + 1;
					if (stage == 0 && n.count != 0)
					{
						const std::uint32_t child = find_edge(t, n, seg, word);
						if (child != kNone)
						{
							if (n.branches > 1)
							{
								stack[sp++] = {node, static_cast<std::uint32_t>(pos), nv, 1};
							}
							node = child;
							pos = next;
							continue;
						}
					}
					if (!seg.empty() && nv < kMaxParams)
					{
						// Both typed children absent (the common case) is one test.
						const bool typed = (n.u64 & n.i64) != kNone;
						if (typed && stage <= 1 && n.u64 != kNone && matches_u64(seg))
						{
							if (n.branches > 1)
							{
								stack[sp++] = {node, static_cast<std::uint32_t>(pos), nv, 2};
							}
							values[nv++] = {seg.data(), seg.size()};
							node = n.u64;
							pos = next;
							stage = 0;
							continue;
						}
						if (typed && stage <= 2 && n.i64 != kNone && matches_i64(seg))
						{
							if (n.branches > 1)
							{
								stack[sp++] = {node, static_cast<std::uint32_t>(pos), nv, 3};
							}
							values[nv++] = {seg.data(), seg.size()};
							node = n.i64;
							pos = next;
							stage = 0;
							continue;
						}
						if (stage <= 3 && n.param != kNone)
						{
							if (n.rest != kNone)
							{
								stack[sp++] = {node, static_cast<std::uint32_t>(pos), nv, 4};
							}
							values[nv++] = {seg.data(), seg.size()};
							node = n.param;
							pos = next;
							stage = 0;
							continue;
						}
					}
					if (n.rest != kNone && nv < kMaxParams && pos < len)
					{
						values[nv++] = {path.data() + pos, len - pos};
						nvalues = nv;
						return t.nodes[n.rest].route;
					}
				}
				if (sp == 0)
				{
					return kNone;
				}
				const Choice c = stack[--sp];
				node = c.node;
				pos = c.pos;
				nv = c.n;
				stage = c.stage;
			}
		}

		constexpr std::uint32_t find_in(const TableView& t, unsigned method, std::string_view path,
		                                std::array<Capture, kMaxParams>& values, std::uint8_t& n) noexcept
		{
			n = 0;
			const std::uint32_t lit = find_literal(t, method, path);
			if (lit != kNone)
			{
				return lit;
			}
			const std::uint32_t root = t.roots[method];
			return root == kNone ? kNone : walk(t, root, path, values, n);
		}
	}  // namespace detail

	namespace detail
	{
		// The methods other than `method` under which the path finds a route (for 405). Out of
		// line: its scratch captures would otherwise sit in every lookup's stack frame.
		MATCHER_ROUTE_R1_NOINLINE constexpr std::uint16_t allowed_methods(const TableView& t, unsigned method,
		                                                                 std::string_view path) noexcept
		{
			std::uint16_t allowed = 0;
			std::uint16_t others = static_cast<std::uint16_t>(t.methods & ~(1u << method));
			std::array<Capture, kMaxParams> scratch;
			if consteval
			{
				scratch.fill(Capture{nullptr, 0});
			}
			while (others != 0)
			{
				const unsigned other = static_cast<unsigned>(std::countr_zero(others));
				others = static_cast<std::uint16_t>(others & (others - 1));
				std::uint8_t k = 0;
				if (find_in(t, other, path, scratch, k) != kNone)
				{
					allowed = static_cast<std::uint16_t>(allowed | (1u << other));
				}
			}
			return allowed;
		}
	}  // namespace detail

	// Looks up one request into m, which may hold an earlier result: every field a reader
	// looks at is set again, and the captured values are written, never zeroed. method is an
	// index below kMethodSlots (0 GET, 1 POST, 2 PUT, 3 DELETE, 4 PATCH, 5 HEAD, 6 OPTIONS,
	// 7 CONNECT, 8 TRACE). A caller that keeps a Match of its own fills it through this, so
	// the 256 bytes of captures are written once and never copied.
	constexpr void find_into(const TableView& t, unsigned method, std::string_view path, Match& m) noexcept
	{
		m.status = Status::NotFound;
		m.count = 0;
		m.allowed = 0;
		m.route = kNone;
		if (method >= kMethodSlots || path.empty() || path[0] != '/')
		{
			return;
		}
		m.route = detail::find_in(t, method, path, m.params, m.count);
		if (m.route != kNone)
		{
			m.status = Status::Found;
			return;
		}
		m.count = 0;
		m.allowed = detail::allowed_methods(t, method, path);
		if (m.allowed != 0)
		{
			m.status = Status::MethodNotAllowed;
		}
	}

	// Looks up one request (find_into on a fresh Match).
	constexpr Match find(const TableView& t, unsigned method, std::string_view path) noexcept
	{
		Match m;
		find_into(t, method, path, m);
		return m;
	}

	// ========================================================================
	// Building a table
	// ========================================================================

	enum class BuildError : std::uint8_t
	{
		None,
		BadPattern,
		BadMethod,
		Duplicate,
		TooLarge
	};

	struct RouteSpec
	{
		unsigned method = 0;
		std::string_view pattern;
		std::uint32_t route = 0;  // the value the lookup returns for this route
	};

	// Every array of a table starts on a 64-byte boundary, in a table built at run time
	// (this allocator) as in one built while compiling (StaticTable), so that the two lay out
	// their nodes, edges and slots against cache lines alike. Constant evaluation takes
	// std::allocator, the only allocator it accepts; the result is copied into StaticTable.
	inline constexpr std::size_t kTableAlign = 64;

	template <class T>
	struct TableAllocator
	{
		using value_type = T;

		constexpr TableAllocator() noexcept = default;
		template <class U>
		constexpr TableAllocator(const TableAllocator<U>&) noexcept
		{
		}

		constexpr T* allocate(std::size_t n)
		{
			if consteval
			{
				return std::allocator<T>{}.allocate(n);
			}
			else
			{
				return static_cast<T*>(::operator new(n * sizeof(T), std::align_val_t{kTableAlign}));
			}
		}
		constexpr void deallocate(T* p, std::size_t n) noexcept
		{
			if consteval
			{
				std::allocator<T>{}.deallocate(p, n);
			}
			else
			{
				::operator delete(p, n * sizeof(T), std::align_val_t{kTableAlign});
			}
		}
		template <class U>
		friend constexpr bool operator==(const TableAllocator&, const TableAllocator<U>&) noexcept
		{
			return true;
		}
	};

	template <class T>
	using TableVector = std::vector<T, TableAllocator<T>>;

	// The flat arrays as vectors: what a run-time table owns, and what a compile-time build
	// fills before copying into fixed-size arrays.
	struct Built
	{
		TableVector<Node> nodes;
		TableVector<Edge> edges;
		TableVector<LiteralSlot> literals;
		TableVector<char> arena;
		std::array<std::uint32_t, kMethodSlots> roots = no_roots();
		std::uint16_t methods = 0;
		std::uint16_t literal_methods = 0;
		BuildError error = BuildError::None;
		std::uint32_t error_route = 0;   // the route (index into the specs) that failed
		std::uint32_t error_other = 0;   // with Duplicate: the route it duplicates

		constexpr TableView view() const noexcept
		{
			return {nodes, edges, literals, std::string_view(arena.data(), arena.size()), roots, methods,
			        literal_methods};
		}
	};

	namespace detail
	{
		struct Entry
		{
			unsigned method;
			Pattern pattern;
			std::uint32_t route;
			std::uint32_t spec;
		};

		// The order a trie is built in: by method, then segment by segment (kind, type, text),
		// a route that ends before another first.
		constexpr int compare_seg(const Segment& a, const Segment& b) noexcept
		{
			if (a.kind != b.kind)
			{
				return a.kind < b.kind ? -1 : 1;
			}
			if (a.kind == SegKind::Typed && a.type != b.type)
			{
				return a.type < b.type ? -1 : 1;
			}
			if (a.kind == SegKind::Literal)
			{
				return a.text < b.text ? -1 : (a.text == b.text ? 0 : 1);
			}
			return 0;  // parameters match the same segments whatever their names
		}

		constexpr bool entry_less(const Entry& a, const Entry& b) noexcept
		{
			if (a.method != b.method)
			{
				return a.method < b.method;
			}
			const std::size_t n = std::min(a.pattern.n, b.pattern.n);
			for (std::size_t i = 0; i < n; ++i)
			{
				const int c = compare_seg(a.pattern.segs[i], b.pattern.segs[i]);
				if (c != 0)
				{
					return c < 0;
				}
			}
			if (a.pattern.n != b.pattern.n)
			{
				return a.pattern.n < b.pattern.n;
			}
			return a.spec < b.spec;
		}

		constexpr bool same_paths(const Entry& a, const Entry& b) noexcept
		{
			if (a.method != b.method || a.pattern.n != b.pattern.n)
			{
				return false;
			}
			for (std::size_t i = 0; i < a.pattern.n; ++i)
			{
				if (compare_seg(a.pattern.segs[i], b.pattern.segs[i]) != 0)
				{
					return false;
				}
			}
			return true;
		}

		constexpr std::size_t pow2_at_least(std::size_t n) noexcept
		{
			std::size_t p = 1;
			while (p < n)
			{
				p <<= 1;
			}
			return p;
		}

		inline constexpr std::size_t kLinearEdges = 8;

		struct TrieBuilder
		{
			Built& out;
			const std::vector<Entry>& entries;

			constexpr std::uint32_t label(std::string_view s)
			{
				const auto off = static_cast<std::uint32_t>(out.arena.size());
				out.arena.insert(out.arena.end(), s.begin(), s.end());
				return off;
			}

			// Builds the node for entries [lo, hi), which share their first `depth` segments.
			constexpr std::uint32_t build(std::size_t lo, std::size_t hi, std::size_t depth)
			{
				const auto self = static_cast<std::uint32_t>(out.nodes.size());
				out.nodes.push_back({});
				std::uint32_t route = kNone;
				// Entries that end here come first in the sort order.
				while (lo < hi && entries[lo].pattern.n == depth)
				{
					route = entries[lo].route;
					++lo;
				}
				// Group the rest by their segment at `depth`.
				std::vector<std::pair<std::size_t, std::size_t>> literal_groups;
				std::array<std::pair<std::size_t, std::size_t>, 4> other{};  // u64, i64, param, rest
				for (auto& o : other)
				{
					o = {0, 0};
				}
				for (std::size_t i = lo; i < hi;)
				{
					std::size_t j = i + 1;
					while (j < hi && compare_seg(entries[i].pattern.segs[depth], entries[j].pattern.segs[depth]) == 0)
					{
						++j;
					}
					const Segment& s = entries[i].pattern.segs[depth];
					switch (s.kind)
					{
						case SegKind::Literal: literal_groups.push_back({i, j}); break;
						case SegKind::Typed: other[s.type == ParamType::U64 ? 0 : 1] = {i, j}; break;
						case SegKind::Param: other[2] = {i, j}; break;
						case SegKind::Rest: other[3] = {i, j}; break;
					}
					i = j;
				}
				const std::size_t count = literal_groups.size();
				const bool hashed = count > kLinearEdges;
				const std::size_t slots = hashed ? pow2_at_least(2 * count) : count;
				const auto first = static_cast<std::uint32_t>(out.edges.size());
				out.edges.resize(out.edges.size() + slots);
				std::uint8_t branches = count ? 1 : 0;
				for (const auto& o : other)
				{
					branches = static_cast<std::uint8_t>(branches + (o.second > o.first ? 1 : 0));
				}
				{
					Node& n = out.nodes[self];
					n.edges = first;
					n.count = static_cast<std::uint32_t>(slots);
					n.hashed = hashed ? 1 : 0;
					n.branches = branches;
					n.route = route;
				}
				for (std::size_t g = 0; g < count; ++g)
				{
					const auto [a, b] = literal_groups[g];
					const std::string_view text = entries[a].pattern.segs[depth].text;
					Edge e;
					e.len = static_cast<std::uint32_t>(text.size());
					e.word = load_at(text, 0);
					e.off = label(text);
					e.child = build(a, b, depth + 1);
					if (!hashed)
					{
						out.edges[first + g] = e;
					}
					else
					{
						const std::size_t mask = slots - 1;
						std::size_t i = static_cast<std::size_t>(edge_hash(e.word, text)) & mask;
						while (out.edges[first + i].child != kNone)
						{
							i = (i + 1) & mask;
						}
						out.edges[first + i] = e;
					}
				}
				std::array<std::uint32_t, 4> kids{kNone, kNone, kNone, kNone};
				for (std::size_t k = 0; k < 4; ++k)
				{
					if (other[k].second > other[k].first)
					{
						kids[k] = build(other[k].first, other[k].second, depth + 1);
					}
				}
				Node& n = out.nodes[self];
				n.u64 = kids[0];
				n.i64 = kids[1];
				n.param = kids[2];
				n.rest = kids[3];
				return self;
			}
		};
	}  // namespace detail

	// Builds a table from routes. Every pattern must parse; two routes of one method that
	// match the same paths are an error (Built::error names them).
	constexpr Built build_table(std::span<const RouteSpec> specs)
	{
		Built out;
		out.roots.fill(kNone);
		std::vector<detail::Entry> trie;
		std::vector<detail::Entry> literal;
		std::vector<detail::Entry> all;
		all.reserve(specs.size());
		std::uint16_t param_methods = 0;  // bit m: some route of method m has a parameter
		for (std::size_t i = 0; i < specs.size(); ++i)
		{
			const RouteSpec& s = specs[i];
			if (s.method >= kMethodSlots)
			{
				out.error = BuildError::BadMethod;
				out.error_route = static_cast<std::uint32_t>(i);
				return out;
			}
			detail::Entry e{s.method, parse_pattern(s.pattern), s.route, static_cast<std::uint32_t>(i)};
			if (!e.pattern.ok())
			{
				out.error = BuildError::BadPattern;
				out.error_route = static_cast<std::uint32_t>(i);
				return out;
			}
			out.methods = static_cast<std::uint16_t>(out.methods | (1u << s.method));
			if (!e.pattern.literal())
			{
				param_methods = static_cast<std::uint16_t>(param_methods | (1u << s.method));
			}
			all.push_back(e);
		}
		// A method whose routes are all literal is answered by the exact-match table alone. A
		// method that also has parameter routes keeps its literal routes in its trie: the walk
		// tries a literal child before a parameter, so it finds a fully literal route first, as
		// rule 5 wants, and the path is read once instead of hashed and then walked.
		for (const auto& e : all)
		{
			(e.pattern.literal() && !(param_methods & (1u << e.method)) ? literal : trie).push_back(e);
		}
		for (auto* list : {&literal, &trie})
		{
			std::sort(list->begin(), list->end(), detail::entry_less);
			for (std::size_t i = 1; i < list->size(); ++i)
			{
				if (detail::same_paths((*list)[i - 1], (*list)[i]))
				{
					out.error = BuildError::Duplicate;
					out.error_route = (*list)[i].spec;
					out.error_other = (*list)[i - 1].spec;
					return out;
				}
			}
		}
		// The literal table: every literal route by method and whole path.
		if (!literal.empty())
		{
			const std::size_t slots = detail::pow2_at_least(2 * literal.size());
			out.literals.resize(slots);
			for (const auto& e : literal)
			{
				const std::string_view path = e.pattern.n == 0 ? std::string_view("/") : specs[e.spec].pattern;
				LiteralSlot s;
				s.hash = detail::path_hash(path, e.method);
				s.len = static_cast<std::uint32_t>(path.size());
				s.off = static_cast<std::uint32_t>(out.arena.size());
				out.arena.insert(out.arena.end(), path.begin(), path.end());
				s.route = e.route;
				s.method = e.method;
				std::size_t i = static_cast<std::size_t>(s.hash) & (slots - 1);
				while (out.literals[i].route != kNone)
				{
					i = (i + 1) & (slots - 1);
				}
				out.literals[i] = s;
				out.literal_methods = static_cast<std::uint16_t>(out.literal_methods | (1u << e.method));
			}
		}
		// One trie per method.
		detail::TrieBuilder b{out, trie};
		for (std::size_t lo = 0; lo < trie.size();)
		{
			std::size_t hi = lo;
			while (hi < trie.size() && trie[hi].method == trie[lo].method)
			{
				++hi;
			}
			out.roots[trie[lo].method] = b.build(lo, hi, 0);
			lo = hi;
		}
		if (out.nodes.size() >= kNone || out.edges.size() >= kNone || out.arena.size() >= kNone)
		{
			out.error = BuildError::TooLarge;
		}
		return out;
	}

	// ========================================================================
	// A table that is a compile-time constant
	// ========================================================================

	struct StaticSizes
	{
		std::size_t nodes = 0;
		std::size_t edges = 0;
		std::size_t literals = 0;
		std::size_t arena = 0;
	};

	template <StaticSizes S>
	struct StaticTable
	{
		alignas(kTableAlign) std::array<Node, S.nodes> nodes{};
		alignas(kTableAlign) std::array<Edge, S.edges> edges{};
		alignas(kTableAlign) std::array<LiteralSlot, S.literals> literals{};
		alignas(kTableAlign) std::array<char, S.arena + 1> arena{};
		std::array<std::uint32_t, kMethodSlots> roots = no_roots();
		std::uint16_t methods = 0;
		std::uint16_t literal_methods = 0;

		constexpr TableView view() const noexcept
		{
			return {nodes, edges, literals, std::string_view(arena.data(), S.arena), roots, methods, literal_methods};
		}
		constexpr Match find(unsigned method, std::string_view path) const noexcept
		{
			return route_r1::find(view(), method, path);
		}
	};

	namespace detail
	{
		// Named so that the compiler's message says what is wrong with a compile-time table.
		inline void compile_time_table_has_a_bad_pattern() {}
		inline void compile_time_table_has_a_bad_method() {}
		inline void compile_time_table_has_duplicate_routes() {}
		inline void compile_time_table_is_too_large() {}

		template <auto& Specs>
		consteval Built checked_build()
		{
			Built b = build_table(std::span<const RouteSpec>(std::data(Specs), std::size(Specs)));
			switch (b.error)
			{
				case BuildError::None: break;
				case BuildError::BadPattern: compile_time_table_has_a_bad_pattern(); break;
				case BuildError::BadMethod: compile_time_table_has_a_bad_method(); break;
				case BuildError::Duplicate: compile_time_table_has_duplicate_routes(); break;
				case BuildError::TooLarge: compile_time_table_is_too_large(); break;
			}
			return b;
		}

		template <auto& Specs>
		consteval StaticSizes static_sizes()
		{
			const Built b = checked_build<Specs>();
			return {b.nodes.size(), b.edges.size(), b.literals.size(), b.arena.size()};
		}
	}  // namespace detail

	// A routing table built while compiling, from a constexpr array of RouteSpec:
	//     static constexpr RouteSpec routes[] = {{0, "/users/{id}", 0}, ...};
	//     static constexpr auto table = make_static_table<routes>();
	// A malformed pattern or a duplicate route stops the compilation.
	template <auto& Specs>
	consteval auto make_static_table()
	{
		constexpr StaticSizes sizes = detail::static_sizes<Specs>();
		const Built b = detail::checked_build<Specs>();
		StaticTable<sizes> t;
		std::copy(b.nodes.begin(), b.nodes.end(), t.nodes.begin());
		std::copy(b.edges.begin(), b.edges.end(), t.edges.begin());
		std::copy(b.literals.begin(), b.literals.end(), t.literals.begin());
		std::copy(b.arena.begin(), b.arena.end(), t.arena.begin());
		t.roots = b.roots;
		t.methods = b.methods;
		t.literal_methods = b.literal_methods;
		return t;
	}

}  // namespace matcher::route_r1
