# Router survey for round 3 (end-to-end block)

Gathered 2026-10-23 by a survey agent with web reads only. Every fact carries its URL. Not yet re-checked.

## How the facts were read

- Sources: the GitHub REST API (read-only GET requests), raw.githubusercontent.com, the crates.io
  API, proxy.golang.org, sum.golang.org, go.dev (release history and download feed), and
  WebFetch for seven pages (oatpp.io twice, the Drogon wiki twice, gin-gonic.com, go.dev gc-guide,
  boost.org). The WebFetch answers come from a summarizing model and are marked "(WebFetch)".
  They need a second read by a person.
- WebSearch was used twice, to find the Drogon wiki page names and the Windows install page; the
  pages it found are cited where used.
- No clone, no archive download, no install, no build. Source files were fetched as text, hashed
  (sha256) or compared function by function (braces matched by script). Most were held in memory
  only; one copy of cpp-httplib's `httplib.h` at v0.58.0 (22,956 lines) was saved as a text file
  in the session's scratch folder (not in the repository) to find line numbers. Nothing was saved
  to the repository except this file.
- "Pin" means the version in `bench/cmake/pins.cmake`, `bench/arms/rust/Cargo.lock` or
  `bench/arms/go/go.mod`. Each pin commit was compared with the tag commit where the pin names a
  commit. Full 40-character match, checked by comparing each pin value with `.sha` from the commits
  API for the tag: Crow, cpp-httplib, glaze, uWebSockets, Oat++, Pistache, Boost.URL, Drogon, gin,
  chi. No mismatch was seen.
- The GitHub compare API lists at most 300 files per comparison. Where a comparison hit that
  limit, the text says so.
- The desktop's MSVC is 19.51.36246 (STATE.md), that is toolset 14.51. Statements about "MSVC"
  below name the toolset the evidence used, where the page names one.
- Today is 2026-10-23. "Newer" means published after the pin.

## 1. Crow v1.3.4

Pin: v1.3.4, released 2026-09-07, commit ae0fef0ee67eec897e401321b99b6dd7cfbdc155
(https://api.github.com/repos/CrowCpp/Crow/releases, https://api.github.com/repos/CrowCpp/Crow/git/tags/cfe92bb464cdc7ca08b403d8782ee8de99df3722).

**A. Windows with MSVC: yes.**
- The CI matrix at the tag has `{ os: windows-latest, compiler: msvc, cxx_stdlib: msvc }` (line 31).
  On Windows it runs `vcpkg install` with triplet x64-windows (lines 59 to 60) and uploads a Windows
  package (lines 181 to 185).
  https://raw.githubusercontent.com/CrowCpp/Crow/v1.3.4/.github/workflows/build_and_test.yml
- vcpkg.json lists the dependencies asio, openssl and zlib.
  https://raw.githubusercontent.com/CrowCpp/Crow/v1.3.4/vcpkg.json
- The CMake option `CROW_USE_BOOST` is OFF by default (line 53), so standalone asio is the default.
  https://raw.githubusercontent.com/CrowCpp/Crow/v1.3.4/CMakeLists.txt
- The docs have a Windows page: Visual Studio plus vcpkg, "Set Debug/Release and x64/x86".
  https://raw.githubusercontent.com/CrowCpp/Crow/v1.3.4/docs/getting_started/setup/windows.md
- Open issues with "windows" in the title: one, #739 (2024-01-07), "on windows ssltests are
  disabled due to path problems for executable". None with "msvc" in the title.
  https://api.github.com/search/issues?q=repo:CrowCpp/Crow+is:issue+is:open+windows+in:title
- The CI job builds the whole project, not the router header alone. The CI log was not read.

**B. Own server: yes.**
- `app.h` lines 447 to 457: `multithreaded()` calls `concurrency(std::thread::hardware_concurrency())`.
  `concurrency(n)` raises any n below 2 to 2 (comment: Crow has a minimum of 2 threads).
  Line 405: the connection timeout defaults to 5 seconds. Lines 482 and 496: `tcp_nodelay(bool)`
  and `websocket_tcp_nodelay(bool)` exist at this tag.
  https://raw.githubusercontent.com/CrowCpp/Crow/v1.3.4/include/crow/app.h
- The app guide chains `.multithreaded().run()`.
  https://raw.githubusercontent.com/CrowCpp/Crow/v1.3.4/docs/guides/app.md
- The logging guide: `app.loglevel(crow::LogLevel::Warning)` hides debug and info logs, and the
  macro `CROW_ENABLE_DEBUG` sets Debug level unless `loglevel()` says otherwise.
  https://raw.githubusercontent.com/CrowCpp/Crow/v1.3.4/docs/guides/logging.md
- No optimization or release-mode advice in `docs/` (a grep of every `docs/**/*.md` for `-O2`,
  `-O3` and `CMAKE_BUILD_TYPE` found only the Windows page's "Set Debug/Release"). The documented
  production setup is therefore `multithreaded()` and a Warning log level, nothing more.

**C, D: not applicable.**

**E. Newer: v1.3.5, a pre-release, 2026-10-03.** `releases/latest` still returns v1.3.4.
- https://api.github.com/repos/CrowCpp/Crow/releases (v1.3.5 `prerelease: true`).
- Compare v1.3.4 to v1.3.5: 37 commits, 28 files, `include/crow/routing.h` +3/-2.
  https://api.github.com/repos/CrowCpp/Crow/compare/v1.3.4...v1.3.5
- Text compare by the agent of `include/crow/routing.h` at both tags: `class Trie` identical
  (15,671 characters), `class Router` identical, `class BaseRule` identical, `class TaggedRule`
  differs (a `std::forward` template argument fix; the release notes list "Fix missing template
  argument in std::forward"). The websocket rule gets one new line. `crow::Trie` is unchanged.
  https://raw.githubusercontent.com/CrowCpp/Crow/v1.3.4/include/crow/routing.h
  https://raw.githubusercontent.com/CrowCpp/Crow/v1.3.5/include/crow/routing.h
  https://api.github.com/repos/CrowCpp/Crow/releases/tags/v1.3.5
- Router file changed: routing.h yes, the Trie no.

**F. Published sha256: none for a source archive.** The v1.3.5 release assets are installers, with
GitHub's computed digests, for example `Crow-1.3.5-win64.exe` sha256
826f34e8a6e1ccc567bd5ff23b6992e00591afe4b96717b9240cca2ae8a7a7cf.
https://api.github.com/repos/CrowCpp/Crow/releases/tags/v1.3.5

## 2. Drogon v1.9.13 (lookup transcribed)

Pin: v1.9.13, released 2026-05-07, commit 4c5430757ea5451a7c38fbbef4b4bef7dbb47f2f.
https://api.github.com/repos/drogonframework/drogon/releases

**A. Windows with MSVC: yes for the library. The arm transcribes the lookup, so the library build
is not what the arm needs.**
- `cmake.yml` at the tag: job `windows/msvc - STATIC` and `SHARED` on `windows-2022` (lines 18 to
  20). It installs dependencies with conan, builds with C++17 and `-DCMAKE_BUILD_TYPE=Debug`, then
  runs `./test.sh -w`.
  https://raw.githubusercontent.com/drogonframework/drogon/v1.9.13/.github/workflows/cmake.yml
- README says Drogon supports Linux, macOS, FreeBSD, OpenBSD, HaikuOS and Windows.
  https://raw.githubusercontent.com/drogonframework/drogon/v1.9.13/README.md
- The wiki install page gives Windows steps with Visual Studio 2019 and conan, and says the build
  type must be the same in conan and cmake (WebFetch).
  https://github.com/drogonframework/drogon/wiki/ENG-02-Installation
- Open issues with "windows" or "msvc" in the title, among them: #2531 (2026-06-09), #2401
  (2025-11-03, "Windows Install Documentation Unclear"), #2395 (2025-10-16, "Serving swagger on
  windows causes exception and crash"), #2108 (2024-07-25, MSVC 2022 error C2039 in
  `trantor::Logger`), #1898, #1726, #1187, #922, #510. Only the first page of results was read.
  https://api.github.com/search/issues?q=repo:drogonframework/drogon+is:issue+is:open+windows+in:title
- Whether the transcribed lookup (`arms/drogon.cpp`) compiles with MSVC depends on the adapter,
  which this survey did not read.

**B. Own server: yes.**
- `setThreadNum(size_t)`: the default is 1, and 0 means one thread per CPU core. The comment adds
  that the number is usually less than or equal to the number of CPU cores. `setLogLevel` is at
  line 1104, `enableReusePort` at line 1581.
  https://raw.githubusercontent.com/drogonframework/drogon/v1.9.13/lib/inc/drogon/HttpAppFramework.h
- `config.example.json`: `number_of_threads` is 1 by default, 0 means the number of CPU cores
  (lines 103 to 105). `log_level` defaults to "DEBUG" and the TRACE level only works in a debug
  build (lines 233 to 235).
  https://raw.githubusercontent.com/drogonframework/drogon/v1.9.13/config.example.json
- The wiki install page says the default is a debug build and gives `cmake -DCMAKE_BUILD_TYPE=Release ..`
  for release (WebFetch).
  https://github.com/drogonframework/drogon/wiki/ENG-02-Installation
- The wiki benchmark page says "Set the number of drogon threads to 16" for a 16-core, 32-thread
  Xeon server (CentOS 7.4, gcc 7.3.0). It does not state build type or logging (WebFetch).
  https://github.com/drogonframework/drogon/wiki/ENG-14-Benchmarks

**C, D: not applicable.**

**E. Newer: v1.9.14, 2026-10-12.** Router file changed: no.
- Compare v1.9.13 to v1.9.14: 59 commits, 140 files. No file with "Router" in the name changed
  except `lib/src/StaticFileRouter.cc` and `.h`.
  https://api.github.com/repos/drogonframework/drogon/compare/v1.9.13...v1.9.14
- The agent hashed the raw files. `lib/src/HttpControllersRouter.cc` is 28,007 bytes with sha256
  9064c8fb2cb9f3ba7196cf351a261cd253b421318165430e0ffe3499028fba54 at both v1.9.13 and v1.9.14, equal
  to `pins.cmake`. `lib/src/HttpControllersRouter.h` is 3,551 bytes with sha256
  f716094fb5decff23e43d75c6d3057611a94a6c99ab394581af3dd8d2568a86f at both.
  https://raw.githubusercontent.com/drogonframework/drogon/v1.9.14/lib/src/HttpControllersRouter.cc
  https://raw.githubusercontent.com/drogonframework/drogon/v1.9.14/lib/src/HttpControllersRouter.h
- The pre-release v1.10.0-beta.3 (2025-12-21) is older than the pin and belongs to the 1.10 line.
  Not compared. https://api.github.com/repos/drogonframework/drogon/releases

**F. Published sha256: none.** The v1.9.14 release has no assets.
https://api.github.com/repos/drogonframework/drogon/releases/tags/v1.9.14

## 3. Oat++ 1.3.1

Pin: 1.3.1, released 2024-12-01, commit 17ef2a7f6c8a932498799b2a5ae5aab2869975c7. The tag
`1.3.0-latest` points at the same commit.
https://api.github.com/repos/oatpp/oatpp/releases, https://api.github.com/repos/oatpp/oatpp/tags

**A. Windows with MSVC: yes (Debug build in CI; Visual Studio 2017 in the docs).**
- `azure-pipelines.yml` at the tag has the job `windows_mem_pool_off`, "Build - Windows", on image
  `windows-latest`: `cmake ..`, then `cmake --build .`, then it runs `oatppAllTests.exe` from
  `build\test\Debug\`. So CI builds the Debug configuration. There is no `.github/workflows`
  folder at this tag (404); the folder holds only `FUNDING.yml`.
  https://raw.githubusercontent.com/oatpp/oatpp/1.3.1/azure-pipelines.yml
- CMake has MSVC code: the option `OATPP_MSVC_LINK_STATIC_RUNTIME` (CMakeLists.txt line 22) and
  `if(MSVC OR MINGW)` linking `wsock32 ws2_32` (src/CMakeLists.txt lines 318 to 319).
  https://raw.githubusercontent.com/oatpp/oatpp/1.3.1/CMakeLists.txt
  https://raw.githubusercontent.com/oatpp/oatpp/1.3.1/src/CMakeLists.txt
- The Windows install page lists "Microsoft Visual Studio (Tested with Visual Studio 2017)" and
  builds with `cmake ..` and `cmake --build . --target INSTALL`; it names Debug as the default
  build type (WebFetch). https://oatpp.io/docs/installation/windows/
- The supported-platforms page lists Windows under "Maintained on regular basis" and credits a
  contributor (WebFetch). https://oatpp.io/supported-platforms/
- Open issues with "windows" in the title: #1092 (2026-08-05, MSYS2 MinGW linker flags `-z`, GCC
  not MSVC), #603 (2022-07-23, "Failed to build oatpp-test.dll with MSVC 16 compiler"), #998, #933,
  #886, #880, #730, #724, #718. No evidence about Visual Studio 2026 or MSVC 19.51.
  https://api.github.com/search/issues?q=repo:oatpp/oatpp+is:issue+is:open+windows+in:title

**B. Own server: yes.**
- `HttpConnectionHandler` makes one thread per connection (header comment, line 38).
  https://raw.githubusercontent.com/oatpp/oatpp/1.3.1/src/oatpp/web/server/HttpConnectionHandler.hpp
- `AsyncHttpConnectionHandler(router, threadCount = Executor::VALUE_SUGGESTED)` (lines 61 and 75).
  The executor picks processor workers = hardware concurrency, I/O workers = half of that (at
  least 1), timer workers = 1, and the event-based I/O worker unless `OATPP_IO_EVENT_INTERFACE_STUB`
  is defined (Executor.cpp lines 130 to 170).
  https://raw.githubusercontent.com/oatpp/oatpp/1.3.1/src/oatpp/web/server/AsyncHttpConnectionHandler.hpp
  https://raw.githubusercontent.com/oatpp/oatpp/1.3.1/src/oatpp/core/async/Executor.cpp
- CMake: `OATPP_DISABLE_ENV_OBJECT_COUNTERS` is described as disabling object counting "for
  Release builds for better performance" (line 38). `OATPP_DISABLE_POOL_ALLOCATIONS` prints a
  warning that it is deprecated and has no effect (lines 67 to 69).
  https://raw.githubusercontent.com/oatpp/oatpp/1.3.1/CMakeLists.txt
- No page that names a "best configuration" was found.

**C, D: not applicable.**

**E. Newer release: none.** The latest release is 1.3.1. The tag list has only `1.3.1`,
`1.3.0-latest`, `1.3.0`, older ones and `v0.18.x-alpha`. `master` (head f83d648fd8, 2025-11-12)
is 105 commits ahead. Its compare listing hit the 300-file limit; within it
`src/oatpp/web/url/mapping/Pattern.cpp`, `Pattern.hpp` and `Router.hpp` changed (include path
moves, `const` qualifiers, a new `Pattern::reconstruct`). Unreleased.
https://api.github.com/repos/oatpp/oatpp/compare/1.3.1...master

**F. Published sha256: none.** The 1.3.1 release has no assets.

## 4. Pistache v0.4.26

Pin: v0.4.26, released 2024-12-23, commit ddffda861aa49012dcda28f1362d0339e718cd52. Note:
`releases/latest` returns v0.4.25 (2024-12-21), although v0.4.26 is a published release.
https://api.github.com/repos/pistacheio/pistache/releases
https://api.github.com/repos/pistacheio/pistache/releases/latest

**A. Windows with MSVC: yes, but through meson scripts and libevent. The two CMake files that the
harness's Linux build uses show no Windows code.**
- README at the tag: "Pistache supports Linux, macOS, Windows and BSD", with a pointer to
  `Building on Windows.txt`.
  https://raw.githubusercontent.com/pistacheio/pistache/v0.4.26/README.md
- `windows.yaml`: job "Windows with Libevent", os `windows-2019` and `windows-latest`, compiler
  `msvc` and `gcc` (lines 33 to 34); it runs `winscripts\msvcsetup.ps1` and starts a Visual
  Studio Developer Prompt before building and testing.
  https://raw.githubusercontent.com/pistacheio/pistache/v0.4.26/.github/workflows/windows.yaml
- `Building on Windows.txt`: built and tested on Windows 11, Windows Server 2022 and 2019; the
  steps are `winscripts\msvcsetup.ps1` then `winscripts\mesbuild.ps1` (meson).
  https://raw.githubusercontent.com/pistacheio/pistache/v0.4.26/Building%20on%20Windows.txt
- `meson.build` accepts host system `windows` and adds `libevent` on Windows (lines 24 to 25 and
  188 to 189). `src/meson.build` has a Windows branch (line 101) that generates the logging
  manifest resources (`pist_winlog.h`, `.res`) and the import library (lines 89 to 109).
  https://raw.githubusercontent.com/pistacheio/pistache/v0.4.26/meson.build
  https://raw.githubusercontent.com/pistacheio/pistache/v0.4.26/src/meson.build
- The two CMake files that build the library, `CMakeLists.txt` (root) and `src/CMakeLists.txt`, do
  not mention WIN32, MSVC, windows or libevent (grep returned nothing), do not call
  `find_package` for libevent (root lines 82 to 106 find Threads, OpenSSL and GTest only), and do
  not generate the Windows resources. `src/CMakeLists.txt` globs `common/*.cc`, `server/*.cc` and
  `client/*.cc`. `tests/CMakeLists.txt` was not read. So the evidence shows the supported Windows
  route is meson, and shows no CMake Windows route; it does not prove that CMake fails on Windows.
  https://raw.githubusercontent.com/pistacheio/pistache/v0.4.26/CMakeLists.txt
  https://raw.githubusercontent.com/pistacheio/pistache/v0.4.26/src/CMakeLists.txt
- Open issues: #1355 (2026-09-22) "Windows builds produce broken import libraries" (the reporter
  maintains the vcpkg port and left Windows disabled; the Pistache author replied that the import
  library works in many situations); #1281 (2025-01-13) "Error compiling pistache on windows".
  https://api.github.com/repos/pistacheio/pistache/issues/1355
  https://api.github.com/search/issues?q=repo:pistacheio/pistache+is:issue+is:open+windows+in:title
- On Windows the server runs on libevent, not epoll. README lists libevent as a dependency.

**B. Own server: yes.**
- `Http::Endpoint::options().threads(N)` (endpoint.h line 32). Other options: `flags`, `backlog`,
  `maxRequestSize` (lines 35 to 44). The example sets `.threads(thr)`.
  https://raw.githubusercontent.com/pistacheio/pistache/v0.4.26/include/pistache/endpoint.h
  https://raw.githubusercontent.com/pistacheio/pistache/v0.4.26/examples/http_server.cc
- README builds with `meson setup build --buildtype=release` (lines 217 to 218). It says Pistache
  is not yet at 1.0 and most of the code is production ready, with the HTTP client the weak part
  (lines 278 to 280).
  https://raw.githubusercontent.com/pistacheio/pistache/v0.4.26/README.md

**C, D: not applicable.**

**E. Newer release: none.** The newest tag and release is v0.4.26. `master` (head
a7b0dc9ec0, 2026-07-11) is 149 commits ahead, 85 files. Router files changed on `master`:
`src/server/router.cc` (+9/-4), `include/pistache/router.h` (+2/-9), `tests/router_test.cc`.
Commit 9354613524 (2026-06-24) "Fix stack exhaustion in router slash normalization" replaces the
`std::regex` based `SegmentTreeNode::sanitizeResource` with a character loop and removes the static
`multiple_slash` regex. At v0.4.26, `sanitizeResource` is called in the request routing function
(router.cc line 526, after the middlewares run and before the tree search; the same call is also
made in `addRoute` and `removeRoute`), so every lookup runs a `std::regex_replace`. The v0.4.26
router is therefore different from `master` on the lookup path. Unreleased.
https://api.github.com/repos/pistacheio/pistache/compare/v0.4.26...master
https://raw.githubusercontent.com/pistacheio/pistache/v0.4.26/src/server/router.cc

**F. Published sha256: none.**

## 5. Boost.URL 1.92.0 example router

Pin: tag boost-1.92.0, commit a34f3a4a1a0e695f679453af71dfc050a59170e6 (committed 2026-05-13).
Boost.URL has no GitHub releases; the tags are the releases.
https://api.github.com/repos/boostorg/url/tags
https://api.github.com/repos/boostorg/url/commits/boost-1.92.0

**A. Windows with MSVC: unknown for the example router. The library is built with MSVC in CI.**
- CI matrix at the tag: compilers `msvc >=14.20` (one per minor), `clang-cl`, `mingw`, factor
  `msvc Shared x86`; a Windows runner entry at line 383. The CMake workflow builds target `tests`
  (line 216). No step names the examples (grep for "example" in `ci.yml` found nothing).
  https://raw.githubusercontent.com/boostorg/url/boost-1.92.0/.github/workflows/ci.yml
- `example/Jamfile` has `# build-project router ;` commented out, so the b2 build does not build
  the router example. `example/CMakeLists.txt` has `add_subdirectory(router)`.
  https://raw.githubusercontent.com/boostorg/url/boost-1.92.0/example/Jamfile
  https://raw.githubusercontent.com/boostorg/url/boost-1.92.0/example/CMakeLists.txt
- `example/router/CMakeLists.txt` builds `router.cpp`, `impl/matches.cpp`, `detail/impl/router.cpp`
  and links Boost::url and Boost::beast. The example includes Beast and Asio headers.
  https://raw.githubusercontent.com/boostorg/url/boost-1.92.0/example/router/CMakeLists.txt
- History of `example/router`: commit 2bae458a79 (2023-06-10) "fix: member of dll interface class
  may not be declared with dll interface", with issue #754 of the same title (the issue body is
  empty). The agent's inference, not stated in either text: the title is MSVC warning wording, so
  the example may have been compiled with MSVC around 2023.
  https://api.github.com/repos/boostorg/url/commits?path=example/router
  https://api.github.com/repos/boostorg/url/issues/754
- vcpkg's `boost` port is at 1.92.0 (read 2026-10-23), so the exact Boost version is available on
  Windows. https://raw.githubusercontent.com/microsoft/vcpkg/master/ports/boost/vcpkg.json
- Open issues with "windows" or "msvc" in the title: none. Closed: #956 and #959 (the example
  router made move-only, 2026-01-20, before the 1.92.0 tag).
  https://api.github.com/search/issues?q=repo:boostorg/url+example+router

**B. Own server: none for production. The example has a toy server.** `router.cpp` declares a
`serve(...)` function with a document root and a `connection` struct, and uses
`asio::io_context ioc(1)` with a blocking `acceptor.accept` loop (lines 44 to 48, 147 to 154). It
is a single-threaded demo, with no thread, build or tuning guidance in it or its CMake.
https://raw.githubusercontent.com/boostorg/url/boost-1.92.0/example/router/router.cpp

**C, D: not applicable.**

**E. Newer release: none.** The tag list starts with `static-pool`, then boost-1.92.0,
boost-1.92.0.beta1, boost-1.91.0. `develop` is 16 commits ahead (31 files); no file in the list
has "router" in its path.
https://api.github.com/repos/boostorg/url/compare/boost-1.92.0...develop

**F. Published sha256: the Boost 1.92.0 release page has a "SHA256 Hash" column that is empty for
every archive (WebFetch).** https://www.boost.org/releases/1.92.0/

## 6. r3, 2.0 branch at 83d362f, with PCRE2 10.49

Pin: branch `2.0`, commit 83d362f80eeae0a5d5064f9db7ae6fd9ad27ea4e (2026-09-15, merge of PR #185,
a dependabot bump). The default branch is `2.0`; the last tag is 1.3.4 and there is no GitHub
release of 2.0.
https://api.github.com/repos/c9s/r3/commits/2.0, https://api.github.com/repos/c9s/r3/branches,
https://api.github.com/repos/c9s/r3/tags

**A. Windows with MSVC: no, by evidence. The sources do not build on Windows unchanged.**
- `src/node.c` includes `<netinet/in.h>` and `<arpa/inet.h>` (lines 7 to 8), calls `inet_pton`,
  and reads `addr6.__in6_u.__u6_addr32[i]` (line 1018), a glibc field name. `asprintf` is used in
  `node.c`, `slug.c` and `str.c`.
  https://raw.githubusercontent.com/c9s/r3/83d362f80eeae0a5d5064f9db7ae6fd9ad27ea4e/src/node.c
- Open issue #175 (2025-02-16) "apple macOS/windows and ios/android build error": on Windows,
  `fatal error: 'netinet/in.h' file not found` at `src/node.c:7`; on macOS, the `__in6_u` error. A
  comment of 2026-05-18 shows a macOS workaround patch only.
  https://api.github.com/repos/c9s/r3/issues/175
- Issue #116 "Windows build - WIP" (2018) is closed; its last comment (2021-10-14) asks the author
  to resolve conflicts, so a Windows port was not merged as far as the thread shows.
  https://api.github.com/repos/c9s/r3/issues/116
- CI has only `ubuntu-latest` jobs (autotools, CMake with Ninja, sanitizers with gcc and clang).
  https://raw.githubusercontent.com/c9s/r3/83d362f80eeae0a5d5064f9db7ae6fd9ad27ea4e/.github/workflows/ci.yml
- Build systems: CMake (`CMakeLists.txt`, C99) and autotools (`configure.ac`, `Makefile.am`). The
  README's install steps are Debian and Ubuntu packages only.
  https://raw.githubusercontent.com/c9s/r3/83d362f80eeae0a5d5064f9db7ae6fd9ad27ea4e/README.md
- PCRE2 itself builds on Windows; that was not checked here.

**B. Own server: none.** The README shows r3 called "in your http server handler" (line 156). The
source folder holds only the router: `edge.c gvc.c json.c list.c match_entry.c memory.c node.c
slug.c str.c token.c` and headers.
https://api.github.com/repos/c9s/r3/contents/src?ref=83d362f80eeae0a5d5064f9db7ae6fd9ad27ea4e

**C, D: not applicable.**

**E. Newer: none.** The head of `2.0` is still 83d362f (the pin). PCRE2's latest release is
pcre2-10.49 (2026-09-28), the pinned one; nothing newer.
https://api.github.com/repos/c9s/r3/commits/2.0
https://api.github.com/repos/PCRE2Project/pcre2/releases

**F. PCRE2 10.49 asset digests (GitHub):** `pcre2-10.49.tar.bz2` sha256
53c156e1ba416a20da8e65395daa132da0d80e76910424caca3fcdae7831d384 (equal to `pins.cmake`),
`pcre2-10.49.tar.gz` 929f0b20e62879252a15886b06c89f1edef61a363cbd5826fb041080a5e557ae,
`pcre2-10.49.zip` 40fa9173e167648fb872beaaeab667c8778eb37fabeefffa99a7753edb1a9479.
https://api.github.com/repos/PCRE2Project/pcre2/releases/tags/pcre2-10.49
For r3 itself: not found.

## 7. uWebSockets v20.80.0 (`uWS::HttpRouter`)

Pin: v20.80.0, released 2026-09-03, commit 3ffd6f44c9c3c92c96345d9f96bd01ba9c025ab5.
https://api.github.com/repos/uNetworking/uWebSockets/releases

**A. Windows with MSVC (cl.exe): unknown. The header uses only the standard library.**
- `src/HttpRouter.h` includes `<map> <vector> <cstring> <string_view> <string> <algorithm> <memory>
  <utility> <iostream>` and `MoveOnlyFunction.h` (lines 21 to 32). A grep for `_MSC_VER`,
  `__GNUC__`, `__attribute`, `__builtin` finds nothing in it. `MoveOnlyFunction.h` includes
  `<functional> <memory> <type_traits>`.
  https://raw.githubusercontent.com/uNetworking/uWebSockets/v20.80.0/src/HttpRouter.h
  https://raw.githubusercontent.com/uNetworking/uWebSockets/v20.80.0/src/MoveOnlyFunction.h
- The Windows CI job `build_windows` (windows-latest) installs libuv with vcpkg, loads
  `ilammy/msvc-dev-cmd`, then sets `CC=clang`, `CXX=clang++`, `WITH_LIBUV=1` and runs `nmake`. So
  CI compiles with clang++, not cl.exe. The root `Makefile` calls itself "the NMake shim for
  Windows (WIP)" and its line 2 comment gives the same clang recipe. `build.c` composes
  `-march=native -O3 ... -std=c++2b` for the C++ and adds `-flto=auto` unless `WITH_LTO=0`, with
  the comment "Windows does not support it".
  https://raw.githubusercontent.com/uNetworking/uWebSockets/v20.80.0/.github/workflows/cpp.yml
  https://raw.githubusercontent.com/uNetworking/uWebSockets/v20.80.0/Makefile
  https://raw.githubusercontent.com/uNetworking/uWebSockets/v20.80.0/build.c
- Issues: #1622 (2023) the maintainer says all CI tests run on Windows, Linux and macOS; #1807
  (2024-11-13, closed) "MSVC warnings" shows a user compiling `MessageParser.h` with MSVC code
  analysis; #995 (2020), #1353 (2021) and #1166 (2021) are older MSVC compile problems. No open
  issue has "windows" or "msvc" in its title.
  https://api.github.com/search/issues?q=repo:uNetworking/uWebSockets+MSVC

**B. Own server: yes (`uWS::App`).**
- README example comment: "One app per thread; spawn as many as you have CPU-cores and let uWS
  share the listening port." The user manual says the library is single threaded, one event loop
  per thread, and that threads can share a port (it "works on Linux").
  https://raw.githubusercontent.com/uNetworking/uWebSockets/v20.80.0/README.md
  https://raw.githubusercontent.com/uNetworking/uWebSockets/v20.80.0/misc/READMORE.md
- The README lists the event-loop integrations libuv, ASIO, GCD and epoll/kqueue. The Windows CI
  recipe uses libuv.
- Build flags: `build.c` (the project's own build driver) uses `-march=native -O3` and LTO by
  default (lines 15 and 24 to 26); the Windows `Makefile` compiles the C with `-O3` (line 18).
  Beyond that no documented best configuration was found.
  https://raw.githubusercontent.com/uNetworking/uWebSockets/v20.80.0/build.c

**C, D: not applicable.**

**E. Newer release: none.** The tags `v21.0.0-alpha1` and `v21.0.0-alpha2` are from 2023-05-10 and
2023-05-12, older than the pin. `master` is 26 commits ahead (head 045bbc11ef, 2026-10-05), 13
files; `src/HttpRouter.h` is not one of them. The agent hashed it: sha256
8ded0be4f7fd1da15409d4bfb03b36b7a5cc619f92aeb5146242e4bbcce55f90 (14,125 bytes) at v20.80.0 and at
`master`.
https://api.github.com/repos/uNetworking/uWebSockets/compare/v20.80.0...master
https://raw.githubusercontent.com/uNetworking/uWebSockets/master/src/HttpRouter.h

**F. Published sha256: none.**

## 8. glaze v9.0.0 (`glz::route_table`)

Pin: v9.0.0, released 2026-09-24, commit d78832c82289c61a9315bfbc35332cec9f4e93ca.
https://api.github.com/repos/stephenberry/glaze/releases

**A. Windows with MSVC: yes on toolset 14.50 by CI. Risk on 14.51, the desktop's toolset.**
- README: requires C++23. "Actions build and test with ... MSVC (Visual Studio 2026 MSVC Build
  Tools 14.50)". MSVC needs the `/Zc:preprocessor` flag. It aims at "the latest version of MSVC".
  https://raw.githubusercontent.com/stephenberry/glaze/v9.0.0/README.md (lines 254 to 268)
- `msvc.yml`: runner `windows-2025-vs2026`, C++23, Debug on every push, Debug and Release on
  merges to main and manual runs; it builds all tests and runs `ctest`. Other Windows workflows:
  `clang-cl.yml`, `msys2.yml`, `windows-header-compatibility.yml`.
  https://raw.githubusercontent.com/stephenberry/glaze/v9.0.0/.github/workflows/msvc.yml
- `tests/CMakeLists.txt` sets `glaze_BUILD_NETWORKING_TESTS` ON by default (line 138), and
  `tests/networking_tests/CMakeLists.txt` adds `http_router_test`, so the MSVC job builds the
  router test.
  https://raw.githubusercontent.com/stephenberry/glaze/v9.0.0/tests/CMakeLists.txt
  https://raw.githubusercontent.com/stephenberry/glaze/v9.0.0/tests/networking_tests/CMakeLists.txt
- **Open issue #2453 (2026-04-08), label "compiler bug": "Glaze compiles with MSVC 14.50 but not
  with 14.51".** The reporter's 14.51 was 19.51.36223.2. The errors are C2672 for
  `ut::operator ""_test` in `tests/jsonrpc_test/jsonrpc_test.cpp`, that is in the test framework,
  not in the router. The maintainer replied "Probably an MSVC regression". A user filed a Visual
  Studio Developer Community report. The issue was open when read. The desktop has 19.51.36246.
  https://api.github.com/repos/stephenberry/glaze/issues/2453
  https://api.github.com/repos/stephenberry/glaze/issues/2453/comments
- Open issue #2182 (2025-12-29) is about MSVC error output after a failed build.
- `include/glaze/net/http_router.hpp` is not a stand-alone header. It includes
  `glaze/json/generic.hpp`, `glaze/net/http.hpp`, `http_headers.hpp`, `url.hpp`, `<future>` and
  `<iostream>` (lines 6 to 22).
  https://raw.githubusercontent.com/stephenberry/glaze/v9.0.0/include/glaze/net/http_router.hpp

**B. Own server: yes (`glz::http_server`, ASIO).**
- `start()` uses `std::thread::hardware_concurrency()` threads (at least 1); `start(n)` gives n
  worker threads; `start(0)` leaves `io_context::run()` to the caller. The "Performance Tuning"
  section calls `server.start(std::thread::hardware_concurrency())`. Keep-alive is on by default
  with a 60 second idle timeout. It needs ASIO (see `asio-setup.md`).
  https://raw.githubusercontent.com/stephenberry/glaze/v9.0.0/docs/networking/http-server.md
- The performance guide: use `-O2` or `-O3`, and `-march=native` if the program runs where it was
  built.
  https://raw.githubusercontent.com/stephenberry/glaze/v9.0.0/docs/optimizing-performance.md

**C, D: not applicable.**

**E. Newer release: none.** v9.0.0 is the newest tag and release. `main` is 53 commits ahead (106
files). `include/glaze/net/http_router.hpp` changed (+43/-6): new `has_root_prefix` and
`has_embedded_nul` checks that reject captures starting with a separator or drive prefix or
holding a NUL, applied to `:param` and wildcard captures. Its sha256 is
41bb47416b1b1ee4eaac93dc84b02fa5e5b005459fc2cc919b6e28adfc5224d9 at v9.0.0 and
91405f14c634c36259858507422fae546eb4ebadb62fa5e4983d73cb0641a997 on `main`. `http_server.hpp` also
changed. Unreleased.
https://api.github.com/repos/stephenberry/glaze/compare/v9.0.0...main

**F. Published sha256: none.**

## 9. cpp-httplib v0.58.0

Pin: v0.58.0, released 2026-09-26, commit 4f3f9ef19be83ae97a5d9a059432dc00e445b7ab.
https://api.github.com/repos/yhirose/cpp-httplib/releases

**A. Windows with MSVC: yes.**
- README: "cpp-httplib officially supports only the latest Visual Studio"; older Visual Studio
  versions, Cygwin and MSYS2 including MinGW "are neither supported nor tested" (lines 1818 to
  1821). Include `httplib.h` before `Windows.h` or define `WIN32_LEAN_AND_MEAN` (lines 1802 to
  1814). The library is described as C++11 and header only (line 5).
  https://raw.githubusercontent.com/yhirose/cpp-httplib/v0.58.0/README.md
- `test.yaml`, job `windows` on `windows-latest`, runs on every push (lines 481 to 530), with
  three configurations (without SSL, with SSL, compiled); `test-32bit.yml` has "Windows 32-bit
  (MSVC x86)".
  https://raw.githubusercontent.com/yhirose/cpp-httplib/v0.58.0/.github/workflows/test.yaml
  https://raw.githubusercontent.com/yhirose/cpp-httplib/v0.58.0/.github/workflows/test-32bit.yml
- README warns that on Windows with misconfigured IPv6, using "localhost" can add up to 2 seconds
  per request, and advises `127.0.0.1` (line 1448). This matters for a loopback load client.
- Open issues with "windows" or "msvc" in the title: none.

**B. Own server: yes (`httplib::Server`).**
- Default task queue is a `ThreadPool` with a base of 8 threads or `hardware_concurrency() - 1`
  (the larger), growing to 4 times that under load; idle dynamic threads exit after 3 seconds. Set
  `CPPHTTPLIB_THREAD_POOL_COUNT` and `CPPHTTPLIB_THREAD_POOL_MAX_COUNT`, or
  `svr.new_task_queue = [] { return new ThreadPool(8, 64); }` (README lines 906 to 935).
  https://raw.githubusercontent.com/yhirose/cpp-httplib/v0.58.0/README.md
- Keep-alive: `set_keep_alive_max_count` defaults to 100 and `set_keep_alive_timeout` to 5 seconds
  (README lines 872 to 876; macros `CPPHTTPLIB_KEEPALIVE_MAX_COUNT 100` and
  `CPPHTTPLIB_KEEPALIVE_TIMEOUT_SECOND 5`). `CPPHTTPLIB_TCP_NODELAY` is `false` (line 164).
  https://raw.githubusercontent.com/yhirose/cpp-httplib/v0.58.0/httplib.h
- The server binds with `SO_REUSEPORT` where available (Linux, macOS) and `SO_REUSEADDR` on
  Windows (README line 352).

**C, D: not applicable.**

**E. Newer releases: v0.59.0 (2026-10-03), v0.60.0 (2026-10-07), v0.60.1 (2026-10-08), v0.61.0
(2026-10-14), v0.62.0 (2026-10-19), v0.63.0 (2026-10-22).** Router file: `httplib.h` changed
(+2671/-1566 from v0.58.0 to v0.63.0, 182 commits). Function-level text compare by the agent of
`httplib.h` at v0.58.0 against each of the six:
- identical in all six: `class MatcherBase`, `class PathParamsMatcher`, `class RegexMatcher`,
  the `PathParamsMatcher` constructor, `PathParamsMatcher::match`, `RegexMatcher::match`,
  `Server::make_matcher`, `Server::dispatch_request`, `Server::dispatch_request_for_content_reader`;
- `Server::routing` is identical up to v0.61.0 and differs in v0.62.0 and v0.63.0 (a new
  `skip_pre_routing` parameter and a `detail::clear_content(res)` refactor of the 413 branch; no
  change to matching).
https://api.github.com/repos/yhirose/cpp-httplib/compare/v0.58.0...v0.63.0
https://raw.githubusercontent.com/yhirose/cpp-httplib/v0.63.0/httplib.h
So for the router: matching code no, the surrounding `Server::routing` yes from v0.62.0.

**F. Published sha256: none.** The releases carry no assets.

## 10. matchit 0.9.2 (Rust)

Pin: 0.9.2, crates.io 2026-04-08, checksum
8863b587001c1b9a8a4e36008cebc6b3612cb1226fe2de94858e06092687b608 (equals `Cargo.lock`). Declared
`rust_version` 1.66. https://crates.io/api/v1/crates/matchit

**A. Windows: yes.** The test workflow has an `os-check` job that runs `cargo test` on
`macos-latest` and `windows-latest`. No platform-specific code was looked for in the crate.
https://raw.githubusercontent.com/ibraheemdev/matchit/v0.9.2/.github/workflows/test.yml

**B. Own server: none.** It is a router crate. For hosting see section C below.

**C. See "Rust hosting".** axum 0.8.9 pins matchit 0.8.4, not 0.9.2.

**D: not applicable.**

**E. Newer release: none.** crates.io `max_version` is 0.9.2; `master` is identical to v0.9.2
(compare status "identical").
https://api.github.com/repos/ibraheemdev/matchit/compare/v0.9.2...master

**F. Checksums:** crates.io gives the checksum above. Earlier versions for reference: 0.8.4
47e1ffaa40ddd1f3ed91f717a33c8c0ee23fff369e3aa8772b9605cc1d22f4c3 (the axum pin), 0.9.1
b3eede3bdf92f3b4f9dc04072a9ce5ab557d5ec9038773bf9ffcd5588b3cc05b.

## 11. actix-router 0.5.4 (Rust)

Pin: 0.5.4, crates.io 2026-02-18, checksum
14f8c75c51892f18d9c46150c5ac7beb81c95f78c8b83a634d49f4ca32551fe7 (equals `Cargo.lock`). Tag
`router-v0.5.4` is commit 6e4e040ee033f330f736dbfe9c4a0c121f8ca94a in the actix-web monorepo.
https://crates.io/api/v1/crates/actix-router
https://api.github.com/repos/actix/actix-web/tags?per_page=100 (the `router-v0.5.4` row)

**A. Windows: yes.** The monorepo CI matrix has `Windows` on `windows-latest` with triple
`x86_64-pc-windows-msvc`.
https://raw.githubusercontent.com/actix/actix-web/router-v0.5.4/.github/workflows/ci.yml

**B. Own server: none in the crate.** actix-web hosts it. See section C.

**C. See "Rust hosting", item 2.** actix-web 4.17.0 requires `actix-router` `0.5.4` with default
features off, so 0.5.4 is inside the range (it is the lowest allowed).

**D: not applicable.**

**E. Newer release: none.** crates.io `max_version` is 0.5.4. The monorepo's `main` is 307 commits
ahead of the tag; within `actix-router/` these changed: `src/de.rs` (+412/-16), `src/path.rs` (+95,
tests), `src/pattern.rs` (+63), `src/resource.rs` (+97/-2), `src/resource_path.rs`, `src/router.rs`
(+72), `src/url.rs`, `Cargo.toml`. Commit d604bcc851 (2026-04-18) adds deserializing paths to
sequences. Which of these touch the lookup was not read. Unreleased.
https://api.github.com/repos/actix/actix-web/compare/6e4e040ee033f330f736dbfe9c4a0c121f8ca94a...main

**F. Checksum:** the crates.io value above. GitHub gives none.

## 12. path-tree 0.8.3 (Rust)

Pin: 0.8.3, crates.io 2025-03-23, checksum
c2a97453bc21a968f722df730bfe11bd08745cb50d1300b0df2bda131dece136 (equals `pins.cmake` and
`Cargo.lock`). 0.8.2 is yanked. GitHub has the tag `v0.8.3` but no release page for it:
`releases/latest` returns v0.8.2 (2024-12-27).
https://crates.io/api/v1/crates/path-tree
https://api.github.com/repos/viz-rs/path-tree/releases/latest

**A. Windows: yes.** `ci.yaml` runs the tests on ubuntu, macos and windows-latest.
https://raw.githubusercontent.com/viz-rs/path-tree/v0.8.3/.github/workflows/ci.yaml

**B. Own server: none.** The README says "Hyper hello example can be found here
(examples/hello.rs)" (line 186). See section C item 3.
https://raw.githubusercontent.com/viz-rs/path-tree/v0.8.3/README.md

**C. See "Rust hosting", item 3** (the README links a hyper example).

**D: not applicable.**

**E. Newer release: none.** crates.io `max_version` is 0.8.3. `main` is 9 commits ahead (head
b4275047bf, 2025-12-12, "fix: required parameter should not be empty (#46)"). Changed: `src/node.rs`
(+50/-10, in the `find` code: a new empty-parameter check and a new branch for a one-or-more
parameter followed by a slash), `src/parser.rs`, `src/lib.rs`, `Cargo.toml`. Unreleased.
https://api.github.com/repos/viz-rs/path-tree/compare/v0.8.3...main

**F. Checksums:** path-tree above; its one dependency smallvec 1.16.2
f9395f0f0eee849a9b707b2f06bb92a6a422090e2123bb2ef8e87a0e61892a8e (`Cargo.lock`).

## 13. httprouter v1.3.0 (Go)

Pin: v1.3.0, 2019-09-30. go.sum hash `h1:U0609e9tgbseu3rBINet9P48AI/D3oJs4dN7jwJOQ1U=`.
https://proxy.golang.org/github.com/julienschmidt/httprouter/@latest
https://sum.golang.org/lookup/github.com/julienschmidt/httprouter@v1.3.0

**A. Windows: yes by nature, no Windows evidence.** No `//go:build`, `syscall` or `x/sys` text in
`tree.go` or `router.go` (grep). The only CI file is `.travis.yml` (Go 1.7 to 1.13, default Linux).
`go.mod` says `go 1.7`.
https://raw.githubusercontent.com/julienschmidt/httprouter/v1.3.0/.travis.yml
https://raw.githubusercontent.com/julienschmidt/httprouter/v1.3.0/go.mod

**B. Own server: none.** `Router` is an `http.Handler`: `var _ http.Handler = New()` (router.go
line 188) and the type comment at line 124. Defaults: `RedirectTrailingSlash`,
`HandleMethodNotAllowed` and `HandleOPTIONS` are all true (lines 194 to 197); handlers take a third
`Params` argument.
https://raw.githubusercontent.com/julienschmidt/httprouter/v1.3.0/router.go

**C: not applicable.**

**D. Yes, implements `http.Handler`** (above).

**E. Newer release: none** (proxy `@latest` is v1.3.0). `master` is 55 commits ahead; `tree.go`
(+330/-311), `router.go` (+108/-18) and `path.go` changed, with sha256 values different from the
pin (tree.go v1.3.0 a8308a46d3e27400848f4e23b34268f9ca42b95d697311352e1e5f3d18312b97, master
de8d3eb17e24faa66d9c01399ed5a8f30257583ebb5446a6ac5c13c0e48d52d6). Unreleased.
https://api.github.com/repos/julienschmidt/httprouter/compare/v1.3.0...master

**F.** The `h1:` hash above is the module hash, not a sha256 of an archive.

## 14. gin v1.12.0 (Go)

Pin: v1.12.0, released 2026-02-28, commit 73726dc606796a025971fe451f0aa6f1b9b847f6. go.sum hash
`h1:b3YAbrZtnf8N//yjKeU2+MQsh2mY5htkZidOM7O0wG8=`.
https://api.github.com/repos/gin-gonic/gin/releases
https://sum.golang.org/lookup/github.com/gin-gonic/gin@v1.12.0

**A. Windows: yes by nature. CI at the tag has no Windows job.** `gin.yml` uses `os: [ubuntu-latest,
macos-latest]` and Go `1.25`, `1.26`. No build constraints in `tree.go` or
`internal/bytesconv/bytesconv.go`. `go.mod` says `go 1.25.0`; the README says Gin needs Go 1.25 or
above.
https://raw.githubusercontent.com/gin-gonic/gin/v1.12.0/.github/workflows/gin.yml
https://raw.githubusercontent.com/gin-gonic/gin/v1.12.0/go.mod

**B. Own server: none.** `Engine` implements `http.Handler` (`func (engine *Engine) ServeHTTP`,
gin.go line 662).
https://raw.githubusercontent.com/gin-gonic/gin/v1.12.0/gin.go

**C: not applicable.**

**D. Documented production setup.**
- `gin.New()` makes an engine with no middleware (line 202); `gin.Default()` adds `Logger()` and
  `Recovery()` (lines 236 to 239) and prints a debug warning.
  https://raw.githubusercontent.com/gin-gonic/gin/v1.12.0/gin.go
- `mode.go`: the environment variable `GIN_MODE` takes `debug`, `release` or `test`; empty means
  debug (test under `go test`); `SetMode` also works; unknown values panic. `IsDebugging()` gates
  debug printing (`debug.go` line 22).
  https://raw.githubusercontent.com/gin-gonic/gin/v1.12.0/mode.go
- The deployment page says to set `GIN_MODE` to `debug`, `release` or `test`, and that
  `gin.SetMode(gin.ReleaseMode)` does the same in code. It gives no advice on threads or logging
  and does not compare `gin.New` with `gin.Default` (WebFetch).
  https://gin-gonic.com/en/docs/deployment/
- The vendored lookup reads no mode (round 2's Appendix B says the same).

**E. Newer release: none** (proxy `@latest` v1.12.0; tags v1.12.0, v1.11.0, ...). `master` is 45
commits ahead. `tree.go` changed (+14/-7): `getValue` now resets the skipped-nodes stack on entry
and uses `append` for it, a fix for a slice bounds panic. sha256 of `tree.go`: pin
89d06fd0d30e5b6531b04af306ce71bec079e3e7446ee0496f2260613ede0fe7 (equals `pins.cmake`), master
993b589b1d9723d996e433b4dc986983b11f6097390a0ebfb6154eebe1bccd52. Unreleased.
https://api.github.com/repos/gin-gonic/gin/compare/v1.12.0...master

**F.** The `h1:` hash above. No archive sha256 is published.

## 15. Go net/http ServeMux (Go 1.27.x)

Round 2 used go1.27.1. The latest patch is **go1.27.3, released 2026-10-19** (security fixes to
`crypto/x509`). The history: go1.27.0 2026-08-19; go1.27.1 2026-09-01; go1.27.2 2026-10-08 (security
and bug fixes including `net/http`); go1.27.3 2026-10-19.
https://go.dev/doc/devel/release

**A. Windows: yes.** Go ships Windows builds of every release: `go1.27.3.windows-amd64.zip` is
listed. ServeMux is platform independent standard library code; its source was not read.
https://go.dev/dl/?mode=json&include=all

**B. Own server: it is `net/http`.** `http.Server` and `http.ListenAndServe` host the mux.

**C: not applicable.**

**D. Documented runtime settings (go1.27.3 sources).**
- GOMAXPROCS: if the environment variable is a positive whole number it is used. Otherwise the
  default comes from the logical CPU count, the CPU affinity mask and, on Linux, the cgroup CPU
  quota. It is never below 2 unless the CPU count or affinity count is below 2. The runtime
  updates the default periodically; setting the variable or calling `GOMAXPROCS` turns the updates
  off. `GODEBUG=containermaxprocs=0` restores `runtime.NumCPU` as the default.
  https://raw.githubusercontent.com/golang/go/go1.27.3/src/runtime/debug.go
- GOGC: "The default is GOGC=100." `GOGC=off` disables the collector; `SetGCPercent` changes it at
  run time. GOMEMLIMIT sets a soft memory limit.
  https://raw.githubusercontent.com/golang/go/go1.27.3/src/runtime/extern.go
- The GC guide explains GOGC as the trade-off between GC CPU and memory, says GOGC can turn the GC
  off ("provided the memory limit does not apply"), and that the memory limit still holds with
  GOGC off (WebFetch). It states no default value; the default comes from the runtime text above.
  https://go.dev/doc/gc-guide

**E. Newer release: go1.27.2 and go1.27.3. ServeMux code: no change; response writing: yes.**
Compare go1.27.1 to go1.27.3: 48 commits, 141 files. `src/net/http/` files changed: `server.go`
(+29/-6), `fs.go`, `transfer.go`, `transport.go` and tests. `pattern.go`, `routing_tree.go`,
`routing_index.go` and `mapping.go` are not in the list. The `server.go` hunks are in
`chunkWriter.writeHeader` (CONNECT handling, HEAD detection from `lastMethod`) and a doc comment on
`MaxHeaderValueCount`; none is in `ServeMux`.
https://api.github.com/repos/golang/go/compare/go1.27.1...go1.27.3

**F. Published sha256 (go.dev download feed):**
- go1.27.3: `go1.27.3.linux-amd64.tar.gz` 65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40;
  `go1.27.3.windows-amd64.zip` f26081f438319757f8a1b46d7d0b2c5ec7583d4038e485e0aa725cfde7885fff.
- go1.27.2: linux-amd64 ecbadb99091a3f46e31f5f934b068b1864eafa7995211b39eaddf76996045fe5; windows-amd64
  1314008898bd40df77af4b014f777f08873dbdfbcd3d92308728ee03304fe04f.
- go1.27.1: linux-amd64 63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445; windows-amd64
  a3911b5e0e1b1053f25ed0675f4c1c6aad1e2bfcf253df2b9be4caabd2edd95d.
- go1.27.0: linux-amd64 675c26c449cbb18fc24b74650de1eabbae6e16f64326fd85a283fb3b58280685; windows-amd64
  f0c0a0d33ba94f4d2c5dbc887334ce678b21813504ddb3aafcb06e60a5a667c4.
https://go.dev/dl/?mode=json&include=all

## 16. chi v5.3.2 (Go)

Pin: v5.3.2, released 2026-08-20, commit 38939062c5df4d3e8814aad1a488983112627ced. go.sum hash
`h1:5YQkICvTCSZ25hoRsyJazN0scjzKGiu4VAUc7H1o1nY=`.
https://api.github.com/repos/go-chi/chi/releases
https://sum.golang.org/lookup/github.com/go-chi/chi/v5@v5.3.2

**A. Windows: yes.** `ci.yml` at the tag runs Go `1.23.x` to `1.26.x` on `ubuntu-latest` and
`windows-latest`. `go.mod` says `go 1.23`.
https://raw.githubusercontent.com/go-chi/chi/v5.3.2/.github/workflows/ci.yml
https://raw.githubusercontent.com/go-chi/chi/v5.3.2/go.mod

**B. Own server: none.** `Mux` implements `http.Handler` (`func (mx *Mux) ServeHTTP`, mux.go line
63; the type comment says it is friendly with the standard library).
https://raw.githubusercontent.com/go-chi/chi/v5.3.2/mux.go

**C: not applicable.**

**D. Yes, an `http.Handler`** (above).

**E. Newer releases: v5.4.0 (2026-10-12) and v5.5.0 (2026-10-14).** The harness vendors `chain.go`,
`chi.go`, `context.go`, `mux.go` and `tree.go` (`pins.cmake`).
- v5.3.2 to v5.4.0: 15 commits. Changed: `tree.go` (+2/-2), `mux.go` (+9/-1), `chi.go` (+9/-7),
  `context.go` (+31/-7). `chain.go` is not in the list.
  https://api.github.com/repos/go-chi/chi/compare/v5.3.2...v5.4.0
- `tree.go` hunk: only `nodes.tailSort` (a loop rewritten with `slices.Backward`). `tailSort` is
  called from `nodes.Sort`, that is on the route insertion side, not in `findRoute`.
  https://raw.githubusercontent.com/go-chi/chi/v5.3.2/tree.go (line 834)
- `mux.go` hunks: `interface{}` to `any`, and a panic when `Mount` mounts a router onto itself.
  The release notes list a `Clone` method on the context, `interface{}` to `any`, and "Bump minimum
  Go to 1.24" (`go.mod` at v5.4.0 says `go 1.24`).
  https://api.github.com/repos/go-chi/chi/releases/tags/v5.4.0
  https://raw.githubusercontent.com/go-chi/chi/v5.4.0/go.mod
- v5.4.0 to v5.5.0: 6 commits, middleware only. `tree.go` is byte-identical in v5.4.0 and v5.5.0
  (sha256 f4b12b63b662fb8e36658172b36b35705cfb24eefae0665635f4fbd52e64fb79). The pin's `tree.go`
  is 790a26ead9f2f9bb93e61f2c7ee588096068a26afcf56e115801753bd7ed230c (equals `pins.cmake`), the pin's
  `mux.go` 3255394e5c4f305b47b81e2e3912caaf58455223fe7a126cec5c494c663adb24 (equals `pins.cmake`),
  and `mux.go` at v5.5.0 is cc44c2d620e6306b16d6d80f5f6c70f02b5814b357a4f5823372818f355ae67d.
  https://api.github.com/repos/go-chi/chi/releases/tags/v5.5.0
- `chi.go` hunks (v5.3.2 to v5.4.0): documentation comments only.
  `context.go` hunks: `chi.URLParam(r, key)` now calls `URLParamFromCtx`; a new `Context.Clone`
  (deep copies of the parameter slices); `Context.URLParam` is rewritten with `slices.Backward`
  (still last match wins). So the parameter read-back path changed in form, not in meaning. No hunk
  in `findRoute`, `routeHTTP` or `ServeHTTP`.
  https://api.github.com/repos/go-chi/chi/compare/v5.3.2...v5.4.0
- Router file changed: four of the five vendored files changed (`tree.go` and `mux.go` as above,
  `chi.go` documentation only, `context.go` as above); `chain.go` did not. The lookup itself
  (`findRoute`) is untouched.

**F. go.sum hashes (sum.golang.org):** v5.4.0 `h1:+ufzvFTGKyin26Or5DLrlIDq4ygIDBVcj7oVNeeaYFE=`,
v5.5.0 `h1:xdKQ1dJmVJsmgahrXSKhUx8NyVPzpwdlyrrQFpMPJgg=`. The v5.3.2 archive sha256 is in `pins.cmake`.
No archive sha256 is published by the project.

## 17. RegexMatcher 2.1.0.0 (the subject)

- The release 2.1.0.0 is dated 2026-10-08 (commit 2ed364a00681b72d8c81aa236e589087c024d639). The
  default branch is `main`. Its head is that same commit: compare 2.1.0.0 to `main` is "identical".
  So there is no release and no commit on the default branch after 2.1.0.0 that touches
  `include/matcher/route*`. Tags 2.0.0.1 and 2.1.0.0 were both published 2026-10-08.
  https://api.github.com/repos/cpp-for-everything/RegexMatcher/releases
  https://api.github.com/repos/cpp-for-everything/RegexMatcher/compare/2.1.0.0...main
- The head commit message reads "docs(readme): the compilers that build the route matcher, and
  those that fail". The README was not read in this survey.
  https://api.github.com/repos/cpp-for-everything/RegexMatcher/commits/main
- The measured commit in `pins.cmake` is d1d73e99b7b26f54ba75354f4880780ece32e8ed (2026-09-30,
  "Revert feat(route): chain nodes (B1')"), not the 2.1.0.0 tag commit 2ed364a0. The two differ:
  compare d1d73e99b to 2.1.0.0 is 19 commits ahead, 18 files. The route matcher files
  (`include/matcher/route.hpp` and `include/matcher/route/*.hpp`, 11 files in the 2.1.0.0 tree) are
  not among them, which agrees with `pins.cmake` ("route matcher is byte for byte that commit's").
  The changed files are `include/matcher/core.hpp` (+677/-42), `include/matcher/impl/core.ipp`,
  `include/matcher/impl/node.ipp` (the regex-set engine), `CMakeLists.txt`, `include/CMakeLists.txt`,
  docs, CI files, `tests/main.cpp`, `tests/utils/test.hpp`, and `tests/route/ct_tables/github_203.hpp`
  (+5). Whether `core.hpp` is included by the route matcher was not checked, so the claim covers the
  route files only. The commit list includes d16f30a81 (the v1 engine pin, 2026-08-30).
  https://api.github.com/repos/cpp-for-everything/RegexMatcher/compare/d1d73e99b7b26f54ba75354f4880780ece32e8ed...2.1.0.0
  https://api.github.com/repos/cpp-for-everything/RegexMatcher/git/trees/2.1.0.0?recursive=1

## Rust hosting (question C)

1. **axum.** Latest release 0.8.9, 2026-04-14, crates.io checksum
   31b698c5f9a010f6573133b09e0de5408834d0c82f8d7475a89fc1867a71cd90, `rust_version` 1.80.
   At tag `axum-v0.8.9`, `axum/Cargo.toml` has `matchit = "=0.8.4"` (line 62), `hyper` `1.1.0`
   optional (line 77), `hyper-util` `0.1.3` with features tokio, server, service (line 78) and
   `tokio` `1.44` (line 85). crates.io lists the same: matchit `=0.8.4`, hyper `^1.1.0`, hyper-util
   `^0.1.3`, tokio `^1.44`. axum's `main` (head 86aa6153e4, 2026-10-19) still says `version =
   "0.8.9"` and pins `matchit = "=0.9.2"` (line 116): unreleased. So no released axum uses matchit
   0.9.2. matchit 0.8.4 checksum: 47e1ffaa40ddd1f3ed91f717a33c8c0ee23fff369e3aa8772b9605cc1d22f4c3.
   https://crates.io/api/v1/crates/axum
   https://raw.githubusercontent.com/tokio-rs/axum/axum-v0.8.9/axum/Cargo.toml
   https://raw.githubusercontent.com/tokio-rs/axum/main/axum/Cargo.toml
   https://crates.io/api/v1/crates/axum/0.8.9/dependencies
2. **actix-web.** Latest release 4.17.0, 2026-10-15, checksum
   67756b0fc99e07b8702b9a856e3d6ec036387243c2ce6310070d1e8f02680bb0, `rust_version` 1.88. At tag
   `actix-web-v4.17.0`, `actix-web/Cargo.toml` line 139: `actix-router = { version = "0.5.4",
   default-features = false, features = ["http"] }`. That is `^0.5.4`, so 0.5.4 is inside (it is the
   minimum). actix-web's default features include `unicode`, which enables `actix-router/unicode`;
   the arm uses actix-router's default features (`http`, `unicode`), so the router is the same
   build. Workers: `HttpServer::workers(num)` sets the number of workers "per bind address"; the
   default is `std::thread::available_parallelism()`; `num` must be greater than 0 (server.rs
   lines 145 to 158). Also `keep_alive`, `backlog` and `max_connections` setters exist (lines 166
   to 201). Dependencies: `actix-http 3.19`, `actix-server 2.7`, `actix-rt 2.6`, `tokio 1.38.2`.
   https://crates.io/api/v1/crates/actix-web
   https://raw.githubusercontent.com/actix/actix-web/actix-web-v4.17.0/actix-web/Cargo.toml
   https://raw.githubusercontent.com/actix/actix-web/actix-web-v4.17.0/actix-web/src/server.rs
3. **path-tree 0.8.3 README.** It does link a hyper example: `examples/hello.rs` (README line 186).
   The example uses `hyper::server::conn::http1`, `hyper_util::rt::TokioIo`, `#[tokio::main]` (the
   default multi-thread runtime), `TcpListener`, and per accepted connection
   `tokio::task::spawn(http1::Builder::new().serve_connection(io, service_fn(...)))`. It prepends
   the method to the path (`"/" + method + path`) and calls `PathTree::find`. Port 3000. The
   `Cargo.toml` dev-dependencies: `hyper = { version = "1", features = ["full"] }`, `hyper-util`
   `0.1` with `tokio`, `http-body-util 0.1`, `tokio 1` with `macros`, `rt-multi-thread`, `net`. The
   repository has no `Cargo.lock` at the tag (contents API 404), so the example pins no hyper
   version. The crate's `include` list omits examples, so the example exists only in git.
   https://raw.githubusercontent.com/viz-rs/path-tree/v0.8.3/README.md
   https://raw.githubusercontent.com/viz-rs/path-tree/v0.8.3/examples/hello.rs
   https://raw.githubusercontent.com/viz-rs/path-tree/v0.8.3/Cargo.toml
4. **hyper, hyper-util, tokio (crates.io, non-yanked latest).**
   - hyper 1.12.0, 2026-10-06, checksum 2c3e324da4c95177d6291d4c8730197c0d1822f8a9766814a4a44fa5ab797c9c,
     `rust_version` 1.63. https://crates.io/api/v1/crates/hyper
   - hyper-util 0.1.21, 2026-09-24, checksum
     ddc03d96684f9226b8a787cdb71488417b53ab5ea8fdb1dac946cb9431cc8bff, `rust_version` 1.85.
     https://crates.io/api/v1/crates/hyper-util
   - tokio 1.54.1, 2026-10-21, checksum
     b52fd3255258d26fac7264ab5a76b53c13367136dc011d3d6ad4f8ed070396a3, `rust_version` 1.85. The
     crates.io list also shows 1.53.3 and 1.51.6 (both 2026-10-13, `rust_version` 1.71). Whether
     those are maintenance lines of older minors was not checked (the agent's guess only).
     https://crates.io/api/v1/crates/tokio
   - hyper's server example at tag v1.12.0, `examples/hello.rs`: `#[tokio::main]`, a
     `TcpListener` accept loop, `tokio::task::spawn` per connection, and
     `http1::Builder::new().timer(TokioTimer::new()).serve_connection(io, service_fn(hello))`. It
     takes `TokioIo` and `TokioTimer` from `benches/support` because `hyper-util` would be a
     cyclic dependency there.
     https://raw.githubusercontent.com/hyperium/hyper/v1.12.0/examples/hello.rs
   - hyper `http1::Builder::keep_alive(bool)` "Enables or disables HTTP/1 keep-alive" and the
     builder default is `h1_keep_alive: true`; `half_close` defaults to false; the builder's
     default `h1_header_read_timeout` is 30 seconds (src/server/conn/http1.rs lines 247 to 277).
     https://raw.githubusercontent.com/hyperium/hyper/v1.12.0/src/server/conn/http1.rs
   - tokio's runtime docs: the multi-thread scheduler starts one worker thread per CPU core by
     default and is "selected by default"; the current-thread scheduler runs everything on the
     current thread: `runtime::Builder::new_current_thread().build()`, or
     `#[tokio::main(flavor = "current_thread")]`. `Builder::worker_threads` default is the number of
     cores available to the system (builder.rs line 540).
     https://raw.githubusercontent.com/tokio-rs/tokio/tokio-1.54.1/tokio/src/runtime/mod.rs
     https://raw.githubusercontent.com/tokio-rs/tokio/tokio-1.54.1/tokio/src/runtime/builder.rs
     https://raw.githubusercontent.com/tokio-rs/tokio/tokio-1.54.1/tokio-macros/src/lib.rs
   - hyper-util 0.1.21 declares `rust_version` 1.85 for the whole crate (crates.io field); the
     desktop's cargo is 1.98.1 (STATE.md), so that is not a limit there.

## Go hosting (question D)

- httprouter v1.3.0: implements `http.Handler` (section 13).
- gin v1.12.0: `Engine` implements `http.Handler`; `gin.New()` is the no-middleware engine,
  `gin.Default()` adds Logger and Recovery; `GIN_MODE=release` (or `gin.SetMode(gin.ReleaseMode)`)
  turns off the debug output (section 14).
- chi v5.3.2: `Mux` implements `http.Handler` (section 16).
- Go: GOMAXPROCS and GOGC text in section 15. Latest Go 1.27.x patch: go1.27.3, 2026-10-19.

## Summary table

| router (pin) | Windows build with MSVC | own server | newer release (version, date) | router file changed |
|---|---|---|---|---|
| Crow v1.3.4 | yes (CI windows-latest msvc, vcpkg asio) | yes | v1.3.5 pre-release, 2026-10-03 | routing.h yes, `crow::Trie` no |
| Drogon v1.9.13 | yes for the library (CI windows-2022 msvc, Debug, conan); the arm transcribes the lookup | yes | v1.9.14, 2026-10-12 | no (sha256 identical) |
| Oat++ 1.3.1 | yes (Azure windows-latest, Debug; docs: Visual Studio 2017) | yes | none (master only) | master: yes (Pattern.cpp, Pattern.hpp, Router.hpp), unreleased |
| Pistache v0.4.26 | yes via meson scripts and libevent (CI msvc, windows-2019 and latest); root and src CMakeLists.txt show no Windows or libevent code (tests/CMakeLists.txt not read); open #1355 | yes | none (master only) | master: yes (regex removed from sanitizeResource), unreleased |
| Boost.URL 1.92.0 example router | unknown (library CI has msvc; the example is not in CI and is off in b2) | no (toy single-thread demo) | none | no (develop untouched) |
| r3 2.0 at 83d362f | no (POSIX headers, glibc field; open #175) | no | none (2.0 head is the pin; PCRE2 10.49 is latest) | no |
| uWebSockets v20.80.0 | unknown for cl.exe (std-only header; CI Windows job uses clang++) | yes | none (master only) | no (sha256 identical on master) |
| glaze v9.0.0 | yes on 14.50 (CI); open #2453: 14.51 fails to build glaze's tests | yes | none (main only) | main: yes (http_router.hpp), unreleased |
| cpp-httplib v0.58.0 | yes (README: latest Visual Studio; CI windows-latest) | yes | v0.59.0 2026-10-03, v0.60.0 2026-10-07, v0.60.1 2026-10-08, v0.61.0 2026-10-14, v0.62.0 2026-10-19, v0.63.0 2026-10-22 | matchers no; `Server::routing` yes from v0.62.0 |
| matchit 0.9.2 | yes (CI windows-latest) | no | none | no (master identical) |
| actix-router 0.5.4 | yes (CI msvc) | no (actix-web) | none | main: yes, unreleased |
| path-tree 0.8.3 | yes (CI windows-latest) | no | none | main: yes (node.rs), unreleased |
| httprouter v1.3.0 | yes by nature, no Windows CI | no | none | master: yes, unreleased |
| gin v1.12.0 | yes by nature, no Windows CI at the tag | no | none | master: yes (tree.go), unreleased |
| Go net/http ServeMux (1.27.x) | yes (Go ships Windows builds) | is net/http | go1.27.2 2026-10-08, go1.27.3 2026-10-19 | mux code no; server.go response writing yes |
| chi v5.3.2 | yes (CI windows-latest) | no | v5.4.0 2026-10-12, v5.5.0 2026-10-14 | four of five vendored files: tree.go (insertion side only), mux.go (Mount check), chi.go (docs), context.go (Clone added, URLParam loop rewritten); chain.go no; `findRoute` untouched |

Pins that are no longer the latest release: Drogon (v1.9.14), cpp-httplib (v0.63.0), chi (v5.5.0),
Go (go1.27.3). Pistache's pin v0.4.26 is newer than GitHub's "latest" marker (v0.4.25). Crow's
latest stable is still v1.3.4.

## Not verified

- The WebFetch answers (oatpp.io supported platforms and Windows pages; Drogon wiki install and
  benchmark pages; gin-gonic.com deployment page; go.dev gc-guide; boost.org release page) come
  from a summarizing model. Read them again before citing.
- No compile test was run anywhere. All "Windows build" statements are CI workflow text, docs or
  issue text. None of the CI evidence names MSVC 19.51 (toolset 14.51). Glaze's README says its CI
  uses 14.50 (its workflow names only the runner `windows-2025-vs2026`), Pistache's runs on
  windows-2019 and windows-latest, the others on "windows-latest" or "windows-2022" without a
  toolset. CI logs were not read, so which toolset ran is not known.
- Glaze issue #2453: whether v9.0.0's `http_router.hpp` or its networking tests build on 19.51
  is not known; the issue's errors were in `tests/jsonrpc_test`, and the issue was open when read.
- uWebSockets `HttpRouter.h` with cl.exe, and Boost.URL's example router with MSVC (CI does not
  build the example as far as `ci.yml` shows; the CMake integration and b2 workflow steps at lines
  233 to 270 were not read in detail), are unknown.
- Pistache on Windows through CMake with a static library: the root and `src/CMakeLists.txt` show
  no Windows or libevent code and `tests/CMakeLists.txt` was not read; the supported route in the
  repository is meson plus libevent. Whether the CMake path works on Windows was not tested. The
  harness's Linux build uses CMake.
- Drogon: only the first page of open Windows issues was read; the transcribed lookup was not
  compiled for MSVC; the `arms/drogon.cpp` adapter was not read.
- Oat++: the compare to `master` hit the 300-file limit; `master` may differ in more router files
  than the three listed. No "best configuration" page for Oat++, Crow or uWebSockets was found.
- actix-router `main`: which of the changed files alter lookup logic was not read. path-tree `main`
  and gin `master` changes were read only as patches; their effect on results was not tested.
- RegexMatcher: that the route files are unchanged between d1d73e99b and 2.1.0.0 is read from the
  compare file list; whether the route matcher includes `include/matcher/core.hpp` (which changed)
  was not checked.
- httprouter and gin on Windows: only a grep for build constraints in two files each, plus the CI
  files. Go ServeMux on Windows: no source read.
- The text compares used a script that matches braces, not a C++ parser. "Identical" means the
  extracted text is the same; a function that the script could not extract was reported as such
  (none failed).
- Checksums: GitHub's `digest` on release assets is computed by GitHub, not published by the
  projects. No project publishes a sha256 for its source archive; the harness computes those. The
  sum.golang.org `h1:` values are module hashes. The Boost release page lists no hashes.
- crates.io API and the `max_version` field were read for matchit, actix-router, path-tree, axum,
  actix-web, hyper, hyper-util and tokio. Whether a yanked or pre-release version is newer was
  checked only through the first rows of each `versions` list.
- hyper's `h1_header_read_timeout` default (30 seconds) was read from the builder's constructor;
  whether it needs a timer was not read.
- The 2026-09-30 round-2 survey (`design/round2/competitor-survey.md`) was not re-run; only the
  facts above were read again.

## Re-check of the claims round 3 uses (2026-10-23, by the session that owns round 3)

Read again directly, not through a summarizing model: GitHub's REST API (`contents`, `compare`,
`releases`), raw files, and go.dev's release list. Plus the builds of this worktree.

| Claim | How it was checked | Result |
|---|---|---|
| r3 at 83d362f does not build on Windows | MSVC 19.51.36246 build of the server | holds: `src/node.c` line 7 includes `netinet/in.h` (C1083) |
| Pistache v0.4.26 does not build with MSVC through its CMake | same build | holds: its CMake passes `-Wextra` to cl (D8021). Its meson route was not tried |
| Crow, Drogon's transcribed lookup, Oat++, uWebSockets' `HttpRouter.h`, glaze's route table and cpp-httplib's matchers build with MSVC 19.51 | same build | hold, with one fix: asio's `asio/include` is a symbolic link to `../include`, which cl cannot follow once unpacked on Windows, so Crow takes `include/` directly (`server/CMakeLists.txt`). The glaze issue #2453 does not hit `http_router.hpp` |
| Boost.URL's example router on Windows | not built: no Boost 1.92.0 headers on the desktop or in the image | unknown |
| Drogon v1.9.14 (2026-10-12) leaves the transcribed file unchanged | `contents/lib/src/HttpControllersRouter.cc?ref=v1.9.14` | holds: blob 885c1f6db22f53cc7f1707c6366459443c0300d5, 28,007 bytes, the pin's blob |
| chi v5.4.0 (2026-10-12) and v5.5.0 (2026-10-14) leave lookup unchanged | `compare/v5.3.2...v5.5.0`, patches of `tree.go` and `mux.go` | holds: `tree.go` rewrites the loop of `tailSort` (insertion order, same behaviour) with `slices.Backward`; `mux.go` changes the pool's `New` signature to `any` and adds a panic to `Mount`. `findRoute` is untouched |
| cpp-httplib v0.59.0 to v0.63.0 leave the matchers unchanged | `httplib.h` at v0.58.0 and v0.63.0 | holds for `MatcherBase`, `PathParamsMatcher` and `RegexMatcher`: the first 3,000 characters of each definition are identical. Six releases: v0.59.0 (10-03), v0.60.0 (10-07), v0.60.1 (10-08), v0.61.0 (10-14), v0.62.0 (10-19), v0.63.0 (10-22) |
| Crow v1.3.5 is a pre-release | `releases` | holds: published 2026-10-03, `prerelease` true |
| Go 1.27.2 and 1.27.3 exist | `go.dev/dl/?mode=json&include=all` | holds (dates not read there) |

Not re-checked here, so not used by round 3's text until they are: the Windows CI statements of the
Rust and Go crates (the programs were built and checked on Windows instead, which is the evidence
round 3 uses), every claim about documented best configurations, and the unreleased changes on
default branches.
