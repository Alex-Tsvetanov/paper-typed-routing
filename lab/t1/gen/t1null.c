// t1null: the null responder that validates t1gen.
//
// It does the least an HTTP/1.1 server can do and still be answered correctly: it
// counts request terminators (CRLFCRLF) in whatever arrived and writes that many copies
// of one canned 200 response, in one send. No parsing, no routing, no allocation per
// request. Whatever rate t1gen reaches against it on a given core split is the ceiling
// of the generator on that split; a server measured at or near that ceiling is being
// measured by the generator, not the other way round.
//
// One SO_REUSEPORT listener and one epoll loop per thread. --port 0 picks a free port
// and prints it. --drop-pipelined answers at most one request per read and discards
// the rest, which imitates a server that loses pipelined requests; t1gen's self-test
// uses it to prove such a server shows up as timeouts rather than as a hung run.
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <unistd.h>

static const char kResponse[] = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 13\r\n\r\nHello, World!";
#define RESP_LEN (sizeof kResponse - 1)
#define BATCH 256
#define RBUF 65536

static _Atomic int g_stop = 0;
static char* g_batch;  // BATCH responses back to back

typedef struct
{
	int fd;
	int match;       // bytes of CRLFCRLF matched at the end of the previous read
	uint64_t owed;   // response bytes still to write
	uint64_t off;    // bytes written so far, modulo RESP_LEN locates the next byte
	bool want_out;
} nconn_t;

typedef struct
{
	int listen_fd;
	bool drop_pipelined;
	uint64_t served;
} nthr_t;

static void on_signal(int sig)
{
	(void)sig;
	atomic_store(&g_stop, 1);
}

static int count_requests(nconn_t* c, const char* p, size_t n)
{
	static const char pat[4] = {'\r', '\n', '\r', '\n'};
	int count = 0;
	int m = c->match;
	for (size_t i = 0; i < n; ++i)
	{
		if (p[i] == pat[m])
		{
			if (++m == 4)
			{
				++count;
				m = 0;
			}
		}
		else
		{
			m = (p[i] == '\r') ? 1 : 0;
		}
	}
	c->match = m;
	return count;
}

static void set_out(int ep, nconn_t* c, bool out)
{
	if (c->want_out == out) return;
	struct epoll_event ev = {.events = EPOLLIN | (out ? EPOLLOUT : 0u), .data.ptr = c};
	epoll_ctl(ep, EPOLL_CTL_MOD, c->fd, &ev);
	c->want_out = out;
}

// 0 ok, -1 close the connection.
static int flush(int ep, nconn_t* c)
{
	while (c->owed > 0)
	{
		const size_t off = (size_t)(c->off % RESP_LEN);
		const size_t avail = BATCH * RESP_LEN - off;
		const size_t n = c->owed < avail ? (size_t)c->owed : avail;
		const ssize_t w = send(c->fd, g_batch + off, n, MSG_NOSIGNAL);
		if (w > 0)
		{
			c->owed -= (uint64_t)w;
			c->off += (uint64_t)w;
			continue;
		}
		if (w < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
		{
			set_out(ep, c, true);
			return 0;
		}
		if (w < 0 && errno == EINTR) continue;
		return -1;
	}
	set_out(ep, c, false);
	return 0;
}

static void close_conn(int ep, nconn_t* c)
{
	epoll_ctl(ep, EPOLL_CTL_DEL, c->fd, NULL);
	close(c->fd);
	free(c);
}

static void* thr_main(void* arg)
{
	nthr_t* t = arg;
	const int ep = epoll_create1(EPOLL_CLOEXEC);
	if (ep < 0) return NULL;
	struct epoll_event lev = {.events = EPOLLIN, .data.ptr = NULL};
	epoll_ctl(ep, EPOLL_CTL_ADD, t->listen_fd, &lev);
	char* buf = malloc(RBUF);
	if (!buf)
	{
		close(ep);
		return NULL;
	}
	// Every live connection, so shutdown can free them all (the leak checker is watching).
	size_t cap = 1024, n_live = 0;
	nconn_t** live = calloc(cap, sizeof *live);
	struct epoll_event evs[256];
	while (!atomic_load(&g_stop) && live)
	{
		const int n = epoll_wait(ep, evs, 256, 100);
		for (int i = 0; i < n; ++i)
		{
			nconn_t* c = evs[i].data.ptr;
			if (c == NULL)
			{
				for (;;)
				{
					const int fd = accept4(t->listen_fd, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
					if (fd < 0) break;
					const int one = 1;
					setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
					nconn_t* nc = calloc(1, sizeof *nc);
					if (!nc)
					{
						close(fd);
						continue;
					}
					nc->fd = fd;
					struct epoll_event ev = {.events = EPOLLIN, .data.ptr = nc};
					if (epoll_ctl(ep, EPOLL_CTL_ADD, fd, &ev) != 0)
					{
						close(fd);
						free(nc);
						continue;
					}
					if (n_live == cap)
					{
						nconn_t** grown = realloc(live, 2 * cap * sizeof *live);
						if (!grown)
						{
							close_conn(ep, nc);
							continue;
						}
						live = grown;
						cap *= 2;
					}
					live[n_live++] = nc;
				}
				continue;
			}
			bool dead = false;
			if (evs[i].events & EPOLLIN)
			{
				const ssize_t r = recv(c->fd, buf, RBUF, 0);
				if (r > 0)
				{
					int k = count_requests(c, buf, (size_t)r);
					if (t->drop_pipelined && k > 1) k = 1;
					t->served += (uint64_t)k;
					c->owed += (uint64_t)k * RESP_LEN;
					if (flush(ep, c) != 0) dead = true;
				}
				else if (r == 0 || (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR))
				{
					dead = true;
				}
			}
			else if (evs[i].events & (EPOLLERR | EPOLLHUP))
			{
				dead = true;
			}
			if (!dead && (evs[i].events & EPOLLOUT) && flush(ep, c) != 0) dead = true;
			if (dead)
			{
				for (size_t j = 0; j < n_live; ++j)
					if (live[j] == c)
					{
						live[j] = live[--n_live];
						break;
					}
				close_conn(ep, c);
			}
		}
	}
	for (size_t j = 0; j < n_live; ++j) close_conn(ep, live[j]);
	free(live);
	free(buf);
	close(ep);
	return NULL;
}

static int make_listener(int port, int backlog)
{
	const int fd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
	if (fd < 0) return -1;
	const int one = 1;
	setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
	setsockopt(fd, SOL_SOCKET, SO_REUSEPORT, &one, sizeof one);
	struct sockaddr_in a;
	memset(&a, 0, sizeof a);
	a.sin_family = AF_INET;
	a.sin_port = htons((uint16_t)port);
	a.sin_addr.s_addr = htonl(INADDR_ANY);
	if (bind(fd, (struct sockaddr*)&a, sizeof a) != 0 || listen(fd, backlog) != 0)
	{
		close(fd);
		return -1;
	}
	return fd;
}

int main(int argc, char** argv)
{
	int port = 8080, threads = 1;
	bool drop = false;
	for (int i = 1; i < argc; ++i)
	{
		if (!strcmp(argv[i], "--port") && i + 1 < argc) port = atoi(argv[++i]);
		else if (!strcmp(argv[i], "--threads") && i + 1 < argc) threads = atoi(argv[++i]);
		else if (!strcmp(argv[i], "--drop-pipelined")) drop = true;
		else
		{
			fprintf(stderr, "usage: t1null [--port P] [--threads N] [--drop-pipelined]\n");
			return 2;
		}
	}
	if (port < 0 || port > 65535 || threads < 1 || threads > 1024)
	{
		fprintf(stderr, "invalid --port or --threads\n");
		return 2;
	}
	struct sigaction sa;
	memset(&sa, 0, sizeof sa);
	sa.sa_handler = on_signal;
	sigaction(SIGTERM, &sa, NULL);
	sigaction(SIGINT, &sa, NULL);
	signal(SIGPIPE, SIG_IGN);

	g_batch = malloc(BATCH * RESP_LEN);
	nthr_t* thr = calloc((size_t)threads, sizeof *thr);
	pthread_t* tids = calloc((size_t)threads, sizeof *tids);
	if (!g_batch || !thr || !tids) return 1;
	for (int i = 0; i < BATCH; ++i) memcpy(g_batch + (size_t)i * RESP_LEN, kResponse, RESP_LEN);

	for (int i = 0; i < threads; ++i)
	{
		thr[i].listen_fd = make_listener(port, 4096);
		if (thr[i].listen_fd < 0)
		{
			fprintf(stderr, "cannot listen on port %d\n", port);
			return 1;
		}
		if (port == 0)
		{
			struct sockaddr_in a;
			socklen_t len = sizeof a;
			getsockname(thr[i].listen_fd, (struct sockaddr*)&a, &len);
			port = ntohs(a.sin_port);
		}
		thr[i].drop_pipelined = drop;
	}
	printf("t1null listening on port %d (%d threads, %zu byte response%s)\n", port, threads, RESP_LEN,
	    drop ? ", dropping pipelined requests" : "");
	fflush(stdout);
	for (int i = 0; i < threads; ++i) pthread_create(&tids[i], NULL, thr_main, &thr[i]);
	uint64_t served = 0;
	for (int i = 0; i < threads; ++i)
	{
		pthread_join(tids[i], NULL);
		served += thr[i].served;
		close(thr[i].listen_fd);
	}
	printf("t1null served %llu responses\n", (unsigned long long)served);
	free(thr);
	free(tids);
	free(g_batch);
	return 0;
}
