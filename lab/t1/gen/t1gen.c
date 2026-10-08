// t1gen: HTTP/1.1 load generator for the T1 tier of the lab (lab/README.md).
//
// Closed loop (default): C keep-alive connections. Each writes --depth requests back to
// back in one send and writes the next batch when the last response of the previous
// batch has arrived (see closed_refill). Depth 1 is plain keep-alive; depth > 1 is
// HTTP/1.1 pipelining. Latency runs from the moment a request was queued on its
// connection to the moment the last byte of its response was parsed.
//
// Open loop (--rate R): requests fall due on a fixed per-thread schedule whether or not
// earlier ones completed. A due request goes to any connection with a free slot and
// waits inside the generator when none has one. Latency is measured from the due time,
// so a stall is charged to every request it delays (no coordinated omission).
//
// Counting. Only the measured window counts. The main thread flips a phase flag after
// the warm-up and again at the end, prints MEASURE_START and MEASURE_END on stdout at
// those instants (the T1 driver snapshots the server there), and reports the raw number
// of 2xx responses completed between them and the wall time between them. No rate is
// computed from anything else.
//
// Targets. One target (--path) or a file of them (--paths), one per line: each connection
// sends the file's targets in order, cyclically, starting at its own share of the file
// (connection i of C at target i*N/C), so every target is requested equally often and a
// server's routing table is exercised as a whole rather than through one route.
//
// Failure is counted, never waited out. A connection that has requests in flight and
// makes no progress for --timeout-ms is closed, its in-flight requests are counted as
// timeouts, and it reconnects. A server that silently drops pipelined requests shows up
// as timeouts, not as a hung run.
//
// Linux only (epoll). Written in C so that MemorySanitizer runs against the libc it
// intercepts, with no uninstrumented standard library in the way.
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/epoll.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#ifndef T1GEN_COMMIT
#define T1GEN_COMMIT "unknown"
#endif

enum { PHASE_WARMUP = 0, PHASE_MEASURE = 1, PHASE_STOP = 2 };
static _Atomic int g_phase = PHASE_WARMUP;

static uint64_t now_ns(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

// ------------------------------------------------------------------ histogram
// Log-linear: exact below 256 ns, then 128 sub-buckets per power of two, so every
// recorded value is within 0.4 percent of the bucket midpoint reported for it.
#define H_SUB_BITS 7
#define H_SUB (1 << H_SUB_BITS)
#define H_BUCKETS (2 * H_SUB + 56 * H_SUB)

typedef struct
{
	uint64_t counts[H_BUCKETS];
	uint64_t n, sum, min, max;
} hist_t;

static int h_index(uint64_t v)
{
	if (v < 2 * H_SUB) return (int)v;
	const int msb = 63 - __builtin_clzll(v);
	const int shift = msb - H_SUB_BITS;
	const uint64_t top = v >> shift;
	return 2 * H_SUB + (msb - (H_SUB_BITS + 1)) * H_SUB + (int)(top - H_SUB);
}

static uint64_t h_value(int idx)
{
	if (idx < 2 * H_SUB) return (uint64_t)idx;
	const int k = idx - 2 * H_SUB;
	const int msb = k / H_SUB + H_SUB_BITS + 1;
	const uint64_t top = (uint64_t)(k % H_SUB + H_SUB);
	const int shift = msb - H_SUB_BITS;
	return (top << shift) + ((1ull << shift) >> 1);
}

static void h_add(hist_t* h, uint64_t v)
{
	h->counts[h_index(v)]++;
	if (h->n == 0 || v < h->min) h->min = v;
	if (v > h->max) h->max = v;
	h->n++;
	h->sum += v;
}

static void h_merge(hist_t* into, const hist_t* from)
{
	for (int i = 0; i < H_BUCKETS; ++i) into->counts[i] += from->counts[i];
	if (from->n)
	{
		if (into->n == 0 || from->min < into->min) into->min = from->min;
		if (from->max > into->max) into->max = from->max;
	}
	into->n += from->n;
	into->sum += from->sum;
}

static uint64_t h_quantile(const hist_t* h, double q)
{
	if (h->n == 0) return 0;
	uint64_t target = (uint64_t)(q * (double)h->n);
	if ((double)target < q * (double)h->n) target++;
	if (target == 0) target = 1;
	uint64_t acc = 0;
	for (int i = 0; i < H_BUCKETS; ++i)
	{
		acc += h->counts[i];
		if (acc >= target)
		{
			const uint64_t v = h_value(i);
			return v > h->max ? h->max : (v < h->min ? h->min : v);
		}
	}
	return h->max;
}

// ------------------------------------------------------------------ options
typedef struct
{
	char host[64];
	int port;
	char path[256];
	char paths[512];
	int threads;
	int connections;
	int depth;
	double warmup_s;
	double duration_s;
	double rate;
	int timeout_ms;
	char cpus[512];
	char out[512];
} opts_t;

static void usage(void)
{
	fprintf(stderr,
	    "usage: t1gen --port P [options]\n"
	    "  --host A          IPv4 literal (default 127.0.0.1)\n"
	    "  --path P          request target (default /)\n"
	    "  --paths FILE      request targets, one per line, sent in order by each connection\n"
	    "                    from its own share of the file (replaces --path)\n"
	    "  --threads N       worker threads (default 1)\n"
	    "  --connections N   keep-alive connections, spread over threads (default 16)\n"
	    "  --depth N         requests in flight per connection, 1 = no pipelining (default 1)\n"
	    "  --warmup S        seconds before the measured window (default 1)\n"
	    "  --duration S      measured window in seconds (default 5)\n"
	    "  --rate R          open loop at R requests/s in total; 0 = closed loop (default 0)\n"
	    "  --timeout-ms N    stall limit per connection with requests in flight (default 1000)\n"
	    "  --cpus LIST       pin thread i to the i-th CPU of a comma list, cyclically\n"
	    "  --out FILE        JSON result (default stdout)\n");
}

static bool parse_long(const char* s, long lo, long hi, long* out)
{
	char* end = NULL;
	errno = 0;
	const long v = strtol(s, &end, 10);
	if (errno || end == s || *end || v < lo || v > hi) return false;
	*out = v;
	return true;
}

static bool parse_double(const char* s, double lo, double hi, double* out)
{
	char* end = NULL;
	errno = 0;
	const double v = strtod(s, &end);
	if (errno || end == s || *end || v < lo || v > hi) return false;
	*out = v;
	return true;
}

static bool copy_arg(char* dst, size_t cap, const char* src)
{
	const size_t n = strlen(src);
	if (n >= cap) return false;
	memcpy(dst, src, n + 1);
	return true;
}

static int parse_opts(int argc, char** argv, opts_t* o)
{
	memset(o, 0, sizeof *o);
	strcpy(o->host, "127.0.0.1");
	strcpy(o->path, "/");
	o->threads = 1;
	o->connections = 16;
	o->depth = 1;
	o->warmup_s = 1.0;
	o->duration_s = 5.0;
	o->timeout_ms = 1000;
	for (int i = 1; i < argc; i += 2)
	{
		const char* a = argv[i];
		const char* v = (i + 1 < argc) ? argv[i + 1] : NULL;
		long l = 0;
		bool ok = v != NULL;
		if (!strcmp(a, "--help") || !strcmp(a, "-h")) { usage(); exit(0); }
		else if (!strcmp(a, "--host")) ok = ok && copy_arg(o->host, sizeof o->host, v);
		else if (!strcmp(a, "--path")) ok = ok && copy_arg(o->path, sizeof o->path, v);
		else if (!strcmp(a, "--paths")) ok = ok && copy_arg(o->paths, sizeof o->paths, v);
		else if (!strcmp(a, "--cpus")) ok = ok && copy_arg(o->cpus, sizeof o->cpus, v);
		else if (!strcmp(a, "--out")) ok = ok && copy_arg(o->out, sizeof o->out, v);
		else if (!strcmp(a, "--port")) { ok = ok && parse_long(v, 1, 65535, &l); o->port = (int)l; }
		else if (!strcmp(a, "--threads")) { ok = ok && parse_long(v, 1, 1024, &l); o->threads = (int)l; }
		else if (!strcmp(a, "--connections")) { ok = ok && parse_long(v, 1, 1000000, &l); o->connections = (int)l; }
		else if (!strcmp(a, "--depth")) { ok = ok && parse_long(v, 1, 1024, &l); o->depth = (int)l; }
		else if (!strcmp(a, "--timeout-ms")) { ok = ok && parse_long(v, 1, 600000, &l); o->timeout_ms = (int)l; }
		else if (!strcmp(a, "--warmup")) ok = ok && parse_double(v, 0.0, 3600.0, &o->warmup_s);
		else if (!strcmp(a, "--duration")) ok = ok && parse_double(v, 0.01, 3600.0, &o->duration_s);
		else if (!strcmp(a, "--rate")) ok = ok && parse_double(v, 0.0, 1e9, &o->rate);
		else { fprintf(stderr, "unknown option: %s\n", a); usage(); return 2; }
		if (!ok) { fprintf(stderr, "invalid or missing value for %s\n", a); return 2; }
	}
	if (o->port == 0) { fprintf(stderr, "--port is required\n"); return 2; }
	if (o->connections < o->threads) o->threads = o->connections;
	return 0;
}

// ------------------------------------------------------------------ request stream
// The requests form a ring: N requests, one per target, g_ring_len bytes in all. A
// connection sends the ring in order from its own start, so a pending write is only a
// count of bytes owed and an offset into the ring. g_reqs holds the ring back to back
// often enough that a whole batch of --depth requests is one contiguous send.
static char* g_reqs;
static size_t g_reqs_len;
static size_t g_ring_len;
static size_t g_nreq;
static size_t* g_req_off;  // offset of request i in the ring
static size_t* g_req_len;  // its length

// ------------------------------------------------------------------ connections
enum { C_CLOSED = 0, C_CONNECTING = 1, C_OPEN = 2 };
#define RBUF_SIZE 32768
#define HEADER_LIMIT 16384

typedef struct
{
	int fd;
	int state;
	int inflight;
	int ts_head;
	int ts_cap;
	uint64_t* ts;
	uint64_t wleft;
	uint64_t woff;
	size_t next_req;  // the ring index of the next request to queue
	bool want_out;
	bool close_after;
	bool in_idle;
	bool ever_open;
	char* rbuf;
	size_t rlen;
	uint64_t body_left;
	bool in_body;
	int status;
	uint64_t last_progress;
	uint64_t retry_at;
	uint64_t connect_start;
} conn_t;

typedef struct
{
	// Request-level losses: timeouts, eof_inflight, sock_err and proto_err count the
	// requests that were in flight when their connection failed that way. The *_events
	// fields count the failures themselves.
	uint64_t completed, non2xx, timeouts, eof_inflight, sock_err, proto_err, connect_err;
	uint64_t sock_events, proto_events, proto_idle, reconnects, bytes, offered, dropped;
} counters_t;

typedef struct
{
	int id;
	int cpu;
	const opts_t* o;
	struct sockaddr_in addr;
	conn_t* conns;
	int nconns;
	int ep;
	counters_t c[2];
	hist_t lat;
	hist_t lag;
	uint64_t* pend;
	size_t pend_cap, pend_head, pend_n, pend_max;
	int* idle;
	int nidle;
	int failed;
} thr_t;

static int ph_index(int ph) { return ph == PHASE_MEASURE ? 1 : 0; }

static void conn_reset(conn_t* c)
{
	c->fd = -1;
	c->state = C_CLOSED;
	c->inflight = 0;
	c->ts_head = 0;
	c->wleft = 0;
	c->woff = g_req_off[c->next_req];  // a reconnection starts on a request boundary
	c->want_out = false;
	c->close_after = false;
	c->rlen = 0;
	c->body_left = 0;
	c->in_body = false;
	c->status = 0;
}

static void conn_drop(thr_t* t, conn_t* c, uint64_t now, uint64_t* inflight_counter, uint64_t retry_delay_ns)
{
	if (inflight_counter) *inflight_counter += (uint64_t)c->inflight;
	if (c->fd >= 0) close(c->fd);
	// Leave the idle list too. A dropped connection that kept its entry and its flag
	// would, once reconnected, never be pushed again (the flag says it is listed) and
	// could sit out the rest of an open-loop run with no counter showing it.
	if (c->in_idle)
	{
		const int self = (int)(c - t->conns);
		for (int i = 0; i < t->nidle; ++i)
		{
			if (t->idle[i] == self)
			{
				t->idle[i] = t->idle[--t->nidle];
				break;
			}
		}
		c->in_idle = false;
	}
	conn_reset(c);
	c->retry_at = now + retry_delay_ns;
}

static void conn_start(thr_t* t, conn_t* c, uint64_t now, int ph)
{
	const int fd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, IPPROTO_TCP);
	if (fd < 0)
	{
		t->c[ph_index(ph)].connect_err++;
		c->retry_at = now + 10000000ull;
		return;
	}
	const int one = 1;
	setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
	if (c->ever_open) t->c[ph_index(ph)].reconnects++;
	c->fd = fd;
	c->connect_start = now;
	c->last_progress = now;
	const int rc = connect(fd, (const struct sockaddr*)&t->addr, sizeof t->addr);
	if (rc != 0 && errno != EINPROGRESS)
	{
		t->c[ph_index(ph)].connect_err++;
		conn_drop(t, c, now, NULL, 10000000ull);
		return;
	}
	struct epoll_event ev = {.events = EPOLLOUT, .data.ptr = c};
	if (epoll_ctl(t->ep, EPOLL_CTL_ADD, fd, &ev) != 0)
	{
		t->c[ph_index(ph)].connect_err++;
		conn_drop(t, c, now, NULL, 10000000ull);
		return;
	}
	c->state = C_CONNECTING;
}

static void set_events(thr_t* t, conn_t* c, bool out)
{
	if (c->want_out == out) return;
	struct epoll_event ev = {.events = EPOLLIN | (out ? EPOLLOUT : 0u), .data.ptr = c};
	epoll_ctl(t->ep, EPOLL_CTL_MOD, c->fd, &ev);
	c->want_out = out;
}

// 0 ok (possibly with bytes still owed), -1 socket error.
static int conn_flush(thr_t* t, conn_t* c)
{
	while (c->wleft > 0)
	{
		const size_t off = (size_t)(c->woff % g_ring_len);
		const size_t avail = g_reqs_len - off;
		const size_t n = c->wleft < avail ? (size_t)c->wleft : avail;
		const ssize_t w = send(c->fd, g_reqs + off, n, MSG_NOSIGNAL);
		if (w > 0)
		{
			c->wleft -= (uint64_t)w;
			c->woff += (uint64_t)w;
			continue;
		}
		if (w < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
		{
			set_events(t, c, true);
			return 0;
		}
		if (w < 0 && errno == EINTR) continue;
		return -1;
	}
	set_events(t, c, false);
	return 0;
}

static void conn_queue(conn_t* c, uint64_t ts)
{
	c->ts[(c->ts_head + c->inflight) % c->ts_cap] = ts;
	c->inflight++;
	c->wleft += g_req_len[c->next_req];
	c->next_req = (c->next_req + 1) % g_nreq;
}

static bool ci_prefix(const char* p, const char* end, const char* lit, size_t n)
{
	return (size_t)(end - p) >= n && strncasecmp(p, lit, n) == 0;
}

// Parses the head [p, hend) where hend points at the terminating CRLFCRLF.
static int parse_head(const char* p, const char* hend, int* status, int64_t* clen, bool* close_after)
{
	if (hend - p < 12 || memcmp(p, "HTTP/1.", 7) != 0) return -1;
	if (p[9] < '0' || p[9] > '9' || p[10] < '0' || p[10] > '9' || p[11] < '0' || p[11] > '9') return -1;
	*status = (p[9] - '0') * 100 + (p[10] - '0') * 10 + (p[11] - '0');
	*clen = -1;
	*close_after = false;
	const char* q = memchr(p, '\n', (size_t)(hend - p));
	while (q && q < hend)
	{
		++q;
		if (q >= hend) break;
		const char* eol = memchr(q, '\r', (size_t)(hend - q));
		if (!eol) eol = hend;
		if (ci_prefix(q, eol, "content-length:", 15))
		{
			const char* v = q + 15;
			while (v < eol && (*v == ' ' || *v == '\t')) ++v;
			int64_t n = 0;
			const char* d = v;
			while (d < eol && *d >= '0' && *d <= '9') n = n * 10 + (*d++ - '0');
			if (d == v) return -1;
			*clen = n;
		}
		else if (ci_prefix(q, eol, "transfer-encoding:", 18))
		{
			return -1;  // chunked or other framings are not expected from these arms
		}
		else if (ci_prefix(q, eol, "connection:", 11))
		{
			for (const char* s = q + 11; s + 5 <= eol; ++s)
				if (strncasecmp(s, "close", 5) == 0) *close_after = true;
		}
		q = memchr(eol, '\n', (size_t)(hend + 2 - eol));
	}
	if (*clen < 0)
	{
		if (*status / 100 == 1 || *status == 204 || *status == 304) *clen = 0;
		else return -1;
	}
	return 0;
}

static int on_response(thr_t* t, conn_t* c, uint64_t now, int ph)
{
	if (c->inflight == 0) return -1;  // a response nobody asked for
	const uint64_t ts = c->ts[c->ts_head];
	c->ts_head = (c->ts_head + 1) % c->ts_cap;
	c->inflight--;
	counters_t* k = &t->c[ph_index(ph)];
	if (c->status / 100 == 2)
	{
		k->completed++;
		if (ph == PHASE_MEASURE) h_add(&t->lat, now >= ts ? now - ts : 0);
	}
	else
	{
		k->non2xx++;
	}
	return 0;
}

// Consumes every complete response in the read buffer. -1 on a protocol error.
static int parse_buffer(thr_t* t, conn_t* c, uint64_t now, int ph)
{
	char* p = c->rbuf;
	char* end = c->rbuf + c->rlen;
	while (p < end)
	{
		if (c->in_body)
		{
			const uint64_t avail = (uint64_t)(end - p);
			const uint64_t take = c->body_left < avail ? c->body_left : avail;
			p += take;
			c->body_left -= take;
			if (c->body_left > 0) break;
			c->in_body = false;
			if (on_response(t, c, now, ph) != 0) return -1;
			continue;
		}
		char* hend = memmem(p, (size_t)(end - p), "\r\n\r\n", 4);
		if (!hend)
		{
			if (end - p > HEADER_LIMIT) return -1;
			break;
		}
		int64_t clen = 0;
		bool close_after = false;
		if (parse_head(p, hend, &c->status, &clen, &close_after) != 0) return -1;
		if (close_after) c->close_after = true;
		p = hend + 4;
		if (clen > 0)
		{
			c->in_body = true;
			c->body_left = (uint64_t)clen;
		}
		else if (on_response(t, c, now, ph) != 0)
		{
			return -1;
		}
	}
	const size_t rest = (size_t)(end - p);
	if (rest && p != c->rbuf) memmove(c->rbuf, p, rest);
	c->rlen = rest;
	return 0;
}

static void idle_push(thr_t* t, conn_t* c)
{
	if (c->in_idle) return;
	c->in_idle = true;
	t->idle[t->nidle++] = (int)(c - t->conns);
}

static conn_t* idle_pop(thr_t* t)
{
	while (t->nidle > 0)
	{
		conn_t* c = &t->conns[t->idle[--t->nidle]];
		c->in_idle = false;
		if (c->state == C_OPEN && !c->close_after && c->inflight < t->o->depth) return c;
	}
	return NULL;
}

// Sends the next batch of --depth requests once the previous batch is fully answered.
//
// A batch, not a sliding window. HTTP/1.1 responses carry no request identity, so a
// client that tops up after every response cannot tell a server that answers every
// request from one that answers only the first request of each read and discards the
// rest: the discarded ones simply never come back, the later ones do, and every
// latency is then paired with the wrong request. With batches, a discarded request
// leaves its batch incomplete, the connection stalls, and the stall is counted as
// timeouts. This is also wrk's pipelining model. Depth 1 is unaffected.
static int closed_refill(thr_t* t, conn_t* c, uint64_t now)
{
	if (c->state != C_OPEN || c->close_after || c->inflight > 0) return 0;
	c->last_progress = now;
	while (c->inflight < t->o->depth) conn_queue(c, now);
	return conn_flush(t, c);
}

static void handle_event(thr_t* t, conn_t* c, uint32_t events, int ph)
{
	const uint64_t now = now_ns();
	counters_t* k = &t->c[ph_index(ph)];
	const bool open_loop = t->o->rate > 0.0;
	if (c->state == C_CONNECTING)
	{
		int err = 0;
		socklen_t len = sizeof err;
		if (getsockopt(c->fd, SOL_SOCKET, SO_ERROR, &err, &len) != 0 || err != 0)
		{
			k->connect_err++;
			conn_drop(t, c, now, NULL, 10000000ull);
			return;
		}
		c->state = C_OPEN;
		c->ever_open = true;
		c->last_progress = now;
		struct epoll_event ev = {.events = EPOLLIN, .data.ptr = c};
		epoll_ctl(t->ep, EPOLL_CTL_MOD, c->fd, &ev);
		c->want_out = false;
		if (open_loop) idle_push(t, c);
		else if (closed_refill(t, c, now) != 0)
		{
			k->sock_events++;
			conn_drop(t, c, now, &k->sock_err, 1000000ull);
		}
		return;
	}
	if (c->state != C_OPEN) return;
	if (events & EPOLLIN)
	{
		for (;;)
		{
			const size_t space = RBUF_SIZE - c->rlen;
			const ssize_t r = recv(c->fd, c->rbuf + c->rlen, space, 0);
			if (r > 0)
			{
				k->bytes += (uint64_t)r;
				c->rlen += (size_t)r;
				c->last_progress = now;
				if (parse_buffer(t, c, now, ph) != 0)
				{
					k->proto_events++;
					if (c->inflight == 0) k->proto_idle++;
					conn_drop(t, c, now, &k->proto_err, 1000000ull);
					return;
				}
				if ((size_t)r < space) break;
				continue;
			}
			if (r == 0)
			{
				// The server closed. Requests still in flight are lost: errors.
				conn_drop(t, c, now, &k->eof_inflight, 0);
				return;
			}
			if (errno == EINTR) continue;
			if (errno == EAGAIN || errno == EWOULDBLOCK) break;
			k->sock_events++;
			conn_drop(t, c, now, &k->sock_err, 1000000ull);
			return;
		}
	}
	else if (events & (EPOLLERR | EPOLLHUP))
	{
		k->sock_events++;
		conn_drop(t, c, now, &k->sock_err, 1000000ull);
		return;
	}
	if ((events & EPOLLOUT) && conn_flush(t, c) != 0)
	{
		k->sock_events++;
		conn_drop(t, c, now, &k->sock_err, 1000000ull);
		return;
	}
	if (open_loop)
	{
		if (!c->close_after && c->inflight < t->o->depth) idle_push(t, c);
	}
	else if (closed_refill(t, c, now) != 0)
	{
		k->sock_events++;
		conn_drop(t, c, now, &k->sock_err, 1000000ull);
	}
}

static void housekeeping(thr_t* t, uint64_t now, int ph)
{
	const uint64_t limit = (uint64_t)t->o->timeout_ms * 1000000ull;
	counters_t* k = &t->c[ph_index(ph)];
	for (int i = 0; i < t->nconns; ++i)
	{
		conn_t* c = &t->conns[i];
		if (c->state == C_CLOSED)
		{
			if (now >= c->retry_at) conn_start(t, c, now, ph);
		}
		else if (c->state == C_CONNECTING)
		{
			if (now - c->connect_start > limit)
			{
				k->connect_err++;
				conn_drop(t, c, now, NULL, 0);
			}
		}
		else if (c->inflight > 0 && now - c->last_progress > limit)
		{
			conn_drop(t, c, now, &k->timeouts, 0);
		}
		else if (c->close_after && c->inflight == 0)
		{
			conn_drop(t, c, now, NULL, 0);
		}
	}
}

static void open_dispatch(thr_t* t, uint64_t now, int ph)
{
	counters_t* k = &t->c[ph_index(ph)];
	while (t->pend_n > 0)
	{
		conn_t* c = idle_pop(t);
		if (!c) break;
		const uint64_t due = t->pend[t->pend_head];
		t->pend_head = (t->pend_head + 1) % t->pend_cap;
		t->pend_n--;
		if (ph == PHASE_MEASURE) h_add(&t->lag, now >= due ? now - due : 0);
		if (c->inflight == 0) c->last_progress = now;
		conn_queue(c, due);
		if (conn_flush(t, c) != 0)
		{
			k->sock_events++;
			conn_drop(t, c, now, &k->sock_err, 1000000ull);
			continue;
		}
		if (c->inflight < t->o->depth) idle_push(t, c);
	}
}

static void* thr_main(void* arg)
{
	thr_t* t = arg;
	const opts_t* o = t->o;
	if (t->cpu >= 0)
	{
		cpu_set_t set;
		CPU_ZERO(&set);
		CPU_SET(t->cpu, &set);
		if (pthread_setaffinity_np(pthread_self(), sizeof set, &set) != 0)
		{
			fprintf(stderr, "thread %d: cannot pin to cpu %d\n", t->id, t->cpu);
			t->failed = 1;
			return NULL;
		}
	}
	prctl(PR_SET_TIMERSLACK, 1UL, 0, 0, 0);
	t->ep = epoll_create1(EPOLL_CLOEXEC);
	if (t->ep < 0)
	{
		t->failed = 1;
		return NULL;
	}
	uint64_t now = now_ns();
	for (int i = 0; i < t->nconns; ++i) conn_start(t, &t->conns[i], now, PHASE_WARMUP);

	const bool open_loop = o->rate > 0.0;
	const double per_thread = open_loop ? o->rate / (double)o->threads : 0.0;
	const uint64_t period = open_loop ? (uint64_t)(1e9 / per_thread) : 0;
	uint64_t next_due = open_loop ? now + (period * (uint64_t)t->id) / (uint64_t)o->threads : 0;
	uint64_t next_house = now + 2000000ull;
	struct epoll_event evs[256];

	for (;;)
	{
		int wait_ms = 5;
		if (open_loop)
		{
			now = now_ns();
			const int ph0 = atomic_load_explicit(&g_phase, memory_order_acquire);
			while (next_due <= now)
			{
				t->c[ph_index(ph0)].offered++;
				if (t->pend_n < t->pend_cap)
				{
					t->pend[(t->pend_head + t->pend_n) % t->pend_cap] = next_due;
					t->pend_n++;
					if (t->pend_n > t->pend_max) t->pend_max = t->pend_n;
				}
				else
				{
					t->c[ph_index(ph0)].dropped++;
				}
				next_due += period;
			}
			open_dispatch(t, now, ph0);
			// Sleep only when the next slot is comfortably far; spin otherwise.
			wait_ms = (next_due > now + 2000000ull) ? 1 : 0;
		}
		const int n = epoll_wait(t->ep, evs, 256, wait_ms);
		// A batch belongs to the phase current when the thread picks it up. That rule
		// applies at both edges of the window (a batch that arrived just before t0 counts
		// as measured, one that arrived just before t1 is not counted), so the window
		// keeps its length and the count is not biased in steady state.
		const int ph = atomic_load_explicit(&g_phase, memory_order_acquire);
		if (ph == PHASE_STOP) break;
		for (int i = 0; i < n; ++i) handle_event(t, (conn_t*)evs[i].data.ptr, evs[i].events, ph);
		now = now_ns();
		if (now >= next_house)
		{
			housekeeping(t, now, ph);
			next_house = now + 2000000ull;
		}
	}
	for (int i = 0; i < t->nconns; ++i)
		if (t->conns[i].fd >= 0) close(t->conns[i].fd);
	close(t->ep);
	return NULL;
}

// ------------------------------------------------------------------ targets

// Appends the request for one target to the ring; 2 on a target that is not one.
static int ring_add(const opts_t* o, const char* target, size_t n, char** ring, size_t* len, size_t* cap)
{
	if (n == 0 || target[0] != '/')
	{
		fprintf(stderr, "a request target must start with '/': %.*s\n", (int)n, target);
		return 2;
	}
	for (size_t i = 0; i < n; ++i)
	{
		if ((unsigned char)target[i] <= ' ' || target[i] == 0x7f)
		{
			fprintf(stderr, "a request target has a space or control byte: %.*s\n", (int)n, target);
			return 2;
		}
	}
	char head[256];
	const int hl = snprintf(head, sizeof head, " HTTP/1.1\r\nHost: %s:%d\r\n\r\n", o->host, o->port);
	if (hl <= 0 || (size_t)hl >= sizeof head || n > 8192) return 2;
	const size_t need = 4 + n + (size_t)hl;
	if (*len + need > *cap)
	{
		size_t nc = *cap ? *cap * 2 : 4096;
		while (nc < *len + need) nc *= 2;
		char* r = realloc(*ring, nc);
		if (!r) return 1;
		*ring = r;
		*cap = nc;
	}
	memcpy(*ring + *len, "GET ", 4);
	memcpy(*ring + *len + 4, target, n);
	memcpy(*ring + *len + 4 + n, head, (size_t)hl);
	*len += need;
	return 0;
}

// Builds the request ring from --path or --paths, then g_reqs.
static int build_ring(const opts_t* o)
{
	char* ring = NULL;
	size_t len = 0, cap = 0, n = 0, ncap = 0;
	size_t* offs = NULL;
	int rc = 0;
	FILE* f = NULL;
	char* line = NULL;
	size_t lcap = 0;
	if (o->paths[0])
	{
		f = fopen(o->paths, "r");
		if (!f)
		{
			fprintf(stderr, "cannot open --paths %s: %s\n", o->paths, strerror(errno));
			return 2;
		}
	}
	for (;;)
	{
		const char* target = o->path;
		size_t tl = strlen(o->path);
		if (f)
		{
			const ssize_t got = getline(&line, &lcap, f);
			if (got < 0) break;
			tl = (size_t)got;
			while (tl > 0 && (line[tl - 1] == '\n' || line[tl - 1] == '\r')) --tl;
			if (tl == 0) continue;  // blank lines are not targets
			target = line;
		}
		if (n == ncap)
		{
			ncap = ncap ? ncap * 2 : 64;
			size_t* no = realloc(offs, (ncap + 1) * sizeof *no);
			if (!no) { rc = 1; break; }
			offs = no;
		}
		offs[n++] = len;
		rc = ring_add(o, target, tl, &ring, &len, &cap);
		if (rc || !f) break;
	}
	free(line);
	if (f) fclose(f);
	if (!rc && n == 0)
	{
		fprintf(stderr, "--paths %s has no targets\n", o->paths);
		rc = 2;
	}
	if (rc)
	{
		free(ring);
		free(offs);
		return rc;
	}
	offs[n] = len;
	g_nreq = n;
	g_ring_len = len;
	g_req_off = offs;
	g_req_len = malloc(n * sizeof *g_req_len);
	if (!g_req_len) return 1;
	for (size_t i = 0; i < n; ++i) g_req_len[i] = offs[i + 1] - offs[i];
	// Enough whole rings that a batch of --depth requests (and a margin) never wraps.
	const size_t rings = ((size_t)o->depth + 64 + n - 1) / n + 1;
	g_reqs_len = len * rings;
	g_reqs = malloc(g_reqs_len);
	if (!g_reqs) return 1;
	for (size_t i = 0; i < rings; ++i) memcpy(g_reqs + i * len, ring, len);
	free(ring);
	return 0;
}

// ------------------------------------------------------------------ main
static void sleep_until(uint64_t deadline)
{
	struct timespec ts = {.tv_sec = (time_t)(deadline / 1000000000ull), .tv_nsec = (long)(deadline % 1000000000ull)};
	while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL) == EINTR) {}
}

static double tv_s(struct timeval tv) { return (double)tv.tv_sec + (double)tv.tv_usec / 1e6; }

static void print_hist_json(FILE* f, const char* name, const hist_t* h, bool sparse)
{
	fprintf(f, "\"%s\":{\"count\":%" PRIu64 ",\"mean\":%.1f,\"min\":%" PRIu64 ",\"p50\":%" PRIu64 ",\"p90\":%" PRIu64
	           ",\"p99\":%" PRIu64 ",\"p999\":%" PRIu64 ",\"max\":%" PRIu64,
	    name, h->n, h->n ? (double)h->sum / (double)h->n : 0.0, h->n ? h->min : 0, h_quantile(h, 0.50),
	    h_quantile(h, 0.90), h_quantile(h, 0.99), h_quantile(h, 0.999), h->max);
	if (sparse)
	{
		fprintf(f, ",\"buckets\":[");
		bool first = true;
		for (int i = 0; i < H_BUCKETS; ++i)
		{
			if (!h->counts[i]) continue;
			fprintf(f, "%s[%" PRIu64 ",%" PRIu64 "]", first ? "" : ",", h_value(i), h->counts[i]);
			first = false;
		}
		fprintf(f, "]");
	}
	fprintf(f, "}");
}

static void print_counters(FILE* f, const char* name, const counters_t* k)
{
	// A protocol failure is an error even when it cost no request in flight; when it did,
	// the lost requests are already in proto_err and the event is not counted again.
	const uint64_t errors =
	    k->timeouts + k->eof_inflight + k->sock_err + k->proto_err + k->non2xx + k->dropped + k->proto_idle;
	fprintf(f,
	    "\"%s\":{\"completed\":%" PRIu64 ",\"non_2xx\":%" PRIu64 ",\"timeouts\":%" PRIu64 ",\"eof_inflight\":%" PRIu64
	    ",\"socket_errors\":%" PRIu64 ",\"protocol_errors\":%" PRIu64 ",\"connect_errors\":%" PRIu64
	    ",\"dropped_slots\":%" PRIu64 ",\"socket_error_events\":%" PRIu64 ",\"protocol_error_events\":%" PRIu64
	    ",\"errors_total\":%" PRIu64 ",\"reconnects\":%" PRIu64 ",\"bytes_read\":%" PRIu64 ",\"offered\":%" PRIu64 "}",
	    name, k->completed, k->non2xx, k->timeouts, k->eof_inflight, k->sock_err, k->proto_err, k->connect_err,
	    k->dropped, k->sock_events, k->proto_events, errors, k->reconnects, k->bytes, k->offered);
}

static void add_counters(counters_t* a, const counters_t* b)
{
	a->completed += b->completed;
	a->non2xx += b->non2xx;
	a->timeouts += b->timeouts;
	a->eof_inflight += b->eof_inflight;
	a->sock_err += b->sock_err;
	a->proto_err += b->proto_err;
	a->connect_err += b->connect_err;
	a->reconnects += b->reconnects;
	a->bytes += b->bytes;
	a->offered += b->offered;
	a->dropped += b->dropped;
	a->sock_events += b->sock_events;
	a->proto_events += b->proto_events;
	a->proto_idle += b->proto_idle;
}

int main(int argc, char** argv)
{
	opts_t o;
	const int prc = parse_opts(argc, argv, &o);
	if (prc) return prc;

	struct sockaddr_in addr;
	memset(&addr, 0, sizeof addr);
	addr.sin_family = AF_INET;
	addr.sin_port = htons((uint16_t)o.port);
	if (inet_pton(AF_INET, o.host, &addr.sin_addr) != 1)
	{
		fprintf(stderr, "--host must be an IPv4 literal\n");
		return 2;
	}

	struct rlimit rl;
	if (getrlimit(RLIMIT_NOFILE, &rl) == 0 && rl.rlim_cur < rl.rlim_max)
	{
		rl.rlim_cur = rl.rlim_max;
		setrlimit(RLIMIT_NOFILE, &rl);
	}

	const int brc = build_ring(&o);
	if (brc) return brc;

	int cpu_list[1024];
	int ncpus = 0;
	if (o.cpus[0])
	{
		char tmp[512];
		strcpy(tmp, o.cpus);
		char* save = NULL;
		for (char* tok = strtok_r(tmp, ",", &save); tok && ncpus < 1024; tok = strtok_r(NULL, ",", &save))
		{
			long v = 0;
			if (!parse_long(tok, 0, CPU_SETSIZE - 1, &v))
			{
				fprintf(stderr, "invalid --cpus entry: %s\n", tok);
				return 2;
			}
			cpu_list[ncpus++] = (int)v;
		}
	}

	thr_t* thr = calloc((size_t)o.threads, sizeof *thr);
	conn_t* conns = calloc((size_t)o.connections, sizeof *conns);
	uint64_t* ts_all = calloc((size_t)o.connections * (size_t)o.depth, sizeof *ts_all);
	char* rbuf_all = malloc((size_t)o.connections * RBUF_SIZE);
	int* idle_all = calloc((size_t)o.connections, sizeof *idle_all);
	pthread_t* tids = calloc((size_t)o.threads, sizeof *tids);
	if (!thr || !conns || !ts_all || !rbuf_all || !idle_all || !tids) return 1;

	// Contiguous slices of the connection array per thread.
	int base = 0;
	for (int i = 0; i < o.threads; ++i)
	{
		thr_t* t = &thr[i];
		t->id = i;
		t->cpu = ncpus ? cpu_list[i % ncpus] : -1;
		t->o = &o;
		t->addr = addr;
		t->nconns = o.connections / o.threads + (i < o.connections % o.threads ? 1 : 0);
		t->conns = &conns[base];
		t->idle = &idle_all[base];
		for (int j = 0; j < t->nconns; ++j)
		{
			conn_t* c = &t->conns[j];
			c->next_req = (size_t)(((uint64_t)(base + j) * g_nreq) / (uint64_t)o.connections);
			conn_reset(c);
			c->ts_cap = o.depth;
			c->ts = &ts_all[(size_t)(base + j) * (size_t)o.depth];
			c->rbuf = &rbuf_all[(size_t)(base + j) * RBUF_SIZE];
		}
		base += t->nconns;
		if (o.rate > 0.0)
		{
			t->pend_cap = 1u << 16;
			t->pend = calloc(t->pend_cap, sizeof *t->pend);
			if (!t->pend) return 1;
		}
	}

	const uint64_t t_launch = now_ns();
	for (int i = 0; i < o.threads; ++i)
	{
		if (pthread_create(&tids[i], NULL, thr_main, &thr[i]) != 0)
		{
			fprintf(stderr, "pthread_create failed\n");
			return 1;
		}
	}

	sleep_until(t_launch + (uint64_t)(o.warmup_s * 1e9));
	struct rusage r0, r1;
	atomic_store_explicit(&g_phase, PHASE_MEASURE, memory_order_release);
	const uint64_t t0 = now_ns();
	getrusage(RUSAGE_SELF, &r0);
	printf("MEASURE_START %" PRIu64 "\n", t0);
	fflush(stdout);

	sleep_until(t0 + (uint64_t)(o.duration_s * 1e9));
	getrusage(RUSAGE_SELF, &r1);
	const uint64_t t1 = now_ns();
	atomic_store_explicit(&g_phase, PHASE_STOP, memory_order_release);
	printf("MEASURE_END %" PRIu64 "\n", t1);
	fflush(stdout);

	int failed = 0;
	for (int i = 0; i < o.threads; ++i)
	{
		pthread_join(tids[i], NULL);
		failed |= thr[i].failed;
	}

	counters_t warm, meas;
	memset(&warm, 0, sizeof warm);
	memset(&meas, 0, sizeof meas);
	hist_t* lat = calloc(1, sizeof *lat);
	hist_t* lag = calloc(1, sizeof *lag);
	if (!lat || !lag) return 1;
	size_t pend_max = 0;
	for (int i = 0; i < o.threads; ++i)
	{
		add_counters(&warm, &thr[i].c[0]);
		add_counters(&meas, &thr[i].c[1]);
		h_merge(lat, &thr[i].lat);
		h_merge(lag, &thr[i].lag);
		if (thr[i].pend_max > pend_max) pend_max = thr[i].pend_max;
	}

	FILE* f = stdout;
	if (o.out[0])
	{
		f = fopen(o.out, "w");
		if (!f)
		{
			fprintf(stderr, "cannot write %s\n", o.out);
			return 1;
		}
	}
	const double wall = (double)(t1 - t0) / 1e9;
	fprintf(f,
	    "{\"tool\":\"t1gen\",\"commit\":\"%s\",\"mode\":\"%s\",\"host\":\"%s\",\"port\":%d,\"path\":\"%s\","
	    "\"paths_file\":\"%s\",\"paths\":%zu,\"ring_bytes\":%zu,\"threads\":%d,\"connections\":%d,\"depth\":%d,\"rate\":%.3f,\"warmup_s\":%.3f,\"duration_s\":%.3f,"
	    "\"timeout_ms\":%d,\"cpus\":\"%s\",\"request_bytes\":%zu,\"t0_ns\":%" PRIu64 ",\"t1_ns\":%" PRIu64
	    ",\"measure_wall_s\":%.9f,",
	    T1GEN_COMMIT, o.rate > 0.0 ? "open" : "closed", o.host, o.port, o.paths[0] ? "" : o.path, o.paths, g_nreq,
	    g_ring_len, o.threads, o.connections, o.depth, o.rate, o.warmup_s, o.duration_s, o.timeout_ms, o.cpus,
	    g_req_len[0], t0, t1, wall);
	print_counters(f, "measure", &meas);
	fprintf(f, ",");
	print_counters(f, "warmup", &warm);
	fprintf(f, ",\"cpu\":{\"user_s\":%.6f,\"sys_s\":%.6f},", tv_s(r1.ru_utime) - tv_s(r0.ru_utime),
	    tv_s(r1.ru_stime) - tv_s(r0.ru_stime));
	print_hist_json(f, "latency_ns", lat, true);
	fprintf(f, ",");
	print_hist_json(f, "issue_lag_ns", lag, false);
	fprintf(f, ",\"pending_max\":%zu,\"thread_failed\":%d}\n", pend_max, failed);
	if (f != stdout) fclose(f);

	for (int i = 0; i < o.threads; ++i) free(thr[i].pend);
	free(lat);
	free(lag);
	free(thr);
	free(conns);
	free(ts_all);
	free(rbuf_all);
	free(idle_all);
	free(tids);
	free(g_reqs);
	free(g_req_off);
	free(g_req_len);
	return failed ? 1 : 0;
}
