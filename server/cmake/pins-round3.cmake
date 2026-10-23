# Round 3's pins: the latest release of each router (Alex, 2026-10-23; design/round3/end-to-end.md,
# section 6), as overrides of round 2's bench/cmake/pins.cmake, which stays as round 2 measured it.
# Included by server/CMakeLists.txt after bench/cmake/pins.cmake. Read 2026-10-23
# (design/round3/router-survey.md, re-check).
#
# Changed:
#   cpp-httplib v0.63.0 (yhirose/cpp-httplib, latest release, 2026-10-22; tag commit below). The
#     sha256 is of the codeload.github.com tarball of that commit, fetched on 2026-10-23 into an
#     empty folder (the project publishes none). Its lookup path is the same as v0.58.0's:
#     MatcherBase, PathParamsMatcher and RegexMatcher with their members, the helpers they call
#     (str_len, pattern) and Request's path_params and matches are identical text.
#   Crow v1.3.5 (CrowCpp/Crow, 2026-10-03, marked a pre-release on GitHub; Alex chose it on
#     2026-10-23). Tag commit below; the sha256 is of the codeload.github.com tarball of that
#     commit, fetched on 2026-10-23 into an empty folder. Its lookup path is the same as v1.3.4's:
#     crow::Trie in include/crow/routing.h is identical text (routing.h changes a websocket
#     payload setting and two std::forward calls), it uses nothing of utility.h but a debug log
#     macro (utility.h changes only its random-string helper), and common.h, which holds
#     routing_params, only adds a constant. asio stays 1.38.2, the latest tag.
#   Drogon v1.9.14 (2026-10-12): lib/src/HttpControllersRouter.cc is the same git blob as at the
#     pin (885c1f6db22f53cc7f1707c6366459443c0300d5), so the transcription and its sha256 stand;
#     only the version label changes.
# Unchanged, already the latest release on 2026-10-23: Oat++ 1.3.1, Pistache v0.4.26, Boost.URL 1.92.0, r3 at 83d362f with PCRE2 10.49,
# uWebSockets v20.80.0, glaze v9.0.0. RegexMatcher stays 2.1.0.0, the measured library. The Go and
# Rust programs pin theirs in their own go.sum and Cargo.lock.
include_guard(GLOBAL)

set(RB_CROW_COMMIT fcf0c360b15fc245d884c71340b08ac20403ba36)
set(RB_CROW_SHA256 ba89e7a4f43772ba447983fb11e91d55376a0b829cba0b2fa98be423945696a4)
set(RB_HTTPLIB_COMMIT 5bcfea7b90575c80a3e54a6967b11b39afa60d5c)
set(RB_HTTPLIB_SHA256 5488830466ddf081f24127d3e2fd1a9abd8e6de96c637113f5a58ac987323b6c)

# The versions the server reports for arms whose round-2 adapter names an older release
# (external.cpp; mserver --router ??). No semicolon or quote in the text: it is a compile definition.
set(MSERVER_ROUND3_VERSIONS "crow=CrowCpp/Crow v1.3.5 (a pre-release) with asio 1.38.2 headers|cpp-httplib=yhirose/cpp-httplib v0.63.0|drogon=drogonframework/drogon v1.9.14, lookup transcribed from a router file unchanged since v1.9.13")
