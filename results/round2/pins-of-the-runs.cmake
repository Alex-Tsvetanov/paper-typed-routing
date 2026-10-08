# Every fetched dependency, pinned by commit and by the sha256 of its source archive.
# A pin changes only with a new baseline; the result lines carry the arm versions.

# nanobench v4.6.0 (martinus/nanobench), header only.
set(RB_NANOBENCH_COMMIT b709728dba4df0356d467abfb0ba20781a8031c0)
set(RB_NANOBENCH_URL "https://codeload.github.com/martinus/nanobench/tar.gz/${RB_NANOBENCH_COMMIT}")
set(RB_NANOBENCH_SHA256 145517050e528a82e3b5d55d5af6fc91e6efa0e486a255a05359a385470a840c)

# Crow v1.3.4 (CrowCpp/Crow, latest release), header only; its router needs the asio
# headers even without I/O: asio 1.38.2 (latest tag).
set(RB_CROW_COMMIT ae0fef0ee67eec897e401321b99b6dd7cfbdc155)
set(RB_CROW_SHA256 d56063a495f2d1a5fec8bc0c72736430645a2bcb38662d29b39355981b8a2000)
set(RB_ASIO_COMMIT 8806a6803cde7054c3049d3666d3ec36786568c5)
set(RB_ASIO_SHA256 ca7f6c14f2bf91e61c7e81fb693f2f8fc86f93e85520d5fc7fd035d0f666bb35)

# Oat++ 1.3.1 (oatpp/oatpp, latest release), built from source with its own CMake.
set(RB_OATPP_COMMIT 17ef2a7f6c8a932498799b2a5ae5aab2869975c7)
set(RB_OATPP_SHA256 633787f10ea5976d41f2b83ad920829ea1f3bd4cb6d5187b2a53ec891e78cde0)

# Boost.URL at tag boost-1.92.0 (boostorg/url): the library sources and example/router; the
# other Boost headers it needs come from the system Boost, which must be exactly 1.92.0.
set(RB_BOOST_URL_COMMIT a34f3a4a1a0e695f679453af71dfc050a59170e6)
set(RB_BOOST_URL_SHA256 b31f8a6f0f5d01ee694109ec0dc4c61f68406b667e5eb70015a4d3686355f025)

# r3 (c9s/r3): the 2.0 branch, its maintained line (the last tag, 1.3.4, is from 2015),
# with PCRE2 10.49 (latest release, 2026-09-28; tag commit 6f9d7c1373262c541324a16a358785b33ef116cf;
# the sha256 is the digest the release page gives for pcre2-10.49.tar.bz2, read 2026-09-30).
# PCRE2 is on r3's lookup path (lab evidence 2026-09-30-L-r3-pcre2-path), so the pin follows its
# release; 10.48 (b6c68fdf6f3ac31388b50aa89ff0fc49c00c987c16e7b5146491d12003f2c8ed) was pinned before.
set(RB_R3_COMMIT 83d362f80eeae0a5d5064f9db7ae6fd9ad27ea4e)
set(RB_R3_SHA256 89289712284d112263f0b1ae29026440bb762b07a4a4e074d5b186c8e8c6af9b)
set(RB_PCRE2_URL "https://github.com/PCRE2Project/pcre2/releases/download/pcre2-10.49/pcre2-10.49.tar.bz2")
set(RB_PCRE2_SHA256 53c156e1ba416a20da8e65395daa132da0d80e76910424caca3fcdae7831d384)

# Pistache v0.4.26 (pistacheio/pistache, latest tag), built with its CMake as a static
# library. Its CMake fetches RapidJSON v1.1.0 by git tag when the system has none.
set(RB_PISTACHE_COMMIT ddffda861aa49012dcda28f1362d0339e718cd52)
set(RB_PISTACHE_SHA256 fb70945cb97e17c724db5483f4fecf2ae29c6cad26d0f4b7647f9880609f0736)

# Drogon v1.9.13 (drogonframework/drogon, commit 4c5430757ea5451a7c38fbbef4b4bef7dbb47f2f,
# latest stable tag): not fetched. Its router needs a running app, so arms/drogon.cpp
# transcribes the lookup from lib/src/HttpControllersRouter.cc at that commit: the file of 770
# lines and 28,007 bytes, sha256 9064c8fb2cb9f3ba7196cf351a261cd253b421318165430e0ffe3499028fba54
# (git blob 885c1f6db22f53cc7f1707c6366459443c0300d5, read 2026-09-30 through the GitHub contents
# API and checked against that blob hash); lines 71-84 (init), 316-333 (addHttpRegex), 335-598
# (addHttpPath) and 600-697 (route).
set(RB_DROGON_ROUTER_SHA256 9064c8fb2cb9f3ba7196cf351a261cd253b421318165430e0ffe3499028fba54)

# RegexMatcher v1, the regex-set engine at d16f30a8 (cpp-for-everything/RegexMatcher, branch
# perf/deterministic-live-sets), for the regexmatcher-v1 reference arm and the paper server's v1
# router arm.
set(RB_REGEXMATCHER_COMMIT_V1 d16f30a81158d620e5a5514087b175a2251e4fa3)
set(RB_REGEXMATCHER_SHA256_V1 2e631b74469e87ff97fe27ffcfd8b938ed6dd1a1d0ee73b0b7aa88b56ecb7108)

# The Go arms (arms/go, one module): httprouter at the version go.sum pins, and
#   nethttp  the ServeMux of Go's standard library, so the Go toolchain is the pin: the
#            version `go version` reports on L ("go version go1.27.1-X:nodwarf5 linux/amd64").
#   gin      gin-gonic/gin v1.12.0 (latest release; tag commit
#            73726dc606796a025971fe451f0aa6f1b9b847f6; source archive
#            https://codeload.github.com/gin-gonic/gin/tar.gz/<commit>, sha256
#            f07b1f86845b2827c9b622c493f9598788b3b36d7945b285269934ab80fa0fa6): tree.go and
#            internal/bytesconv/bytesconv.go vendored unchanged in arms/go/gin, with their
#            sha256 below (checked at configure time, cmake/arm-gin.cmake).
set(RB_NETHTTP_GO "go1.27.1-X:nodwarf5")
set(RB_GIN_TAG v1.12.0)
set(RB_GIN_COMMIT 73726dc606796a025971fe451f0aa6f1b9b847f6)
set(RB_GIN_SHA256 f07b1f86845b2827c9b622c493f9598788b3b36d7945b285269934ab80fa0fa6)
set(RB_GIN_SHA256_tree_go 89d06fd0d30e5b6531b04af306ce71bec079e3e7446ee0496f2260613ede0fe7)
set(RB_GIN_SHA256_internal_bytesconv_bytesconv_go efca594b11389030979a5e90083f5d6d3119356b923195d3c31dcb65b162b3e2)

# The Rust arms (arms/rust, one crate), at the versions Cargo.lock pins with the crates.io
# checksum of each crate: matchit 0.9.2, and actix-router 0.5.4 (latest on crates.io;
# checksum 14f8c75c51892f18d9c46150c5ac7beb81c95f78c8b83a634d49f4ca32551fe7).

# RegexMatcher v2 (cpp-for-everything/RegexMatcher), the route matcher the paper measures. Until
# it is public the arms build from a checkout (REGEXMATCHER_DIR); then the release is pinned here
# by commit and archive sha256, like every other dependency.
set(RB_REGEXMATCHER_V2_COMMIT "")
set(RB_REGEXMATCHER_V2_SHA256 "")

# Added in round 2 (design/round2/hypotheses-v2-proposal.md, section 4). Each archive is the
# codeload.github.com tarball of the project's official repository at the tag's commit; the
# sha256 was computed from the archive fetched on 2026-09-30, and FetchContent verifies it.
# uWebSockets v20.80.0 (uNetworking/uWebSockets, latest release): uWS::HttpRouter, header only.
set(RB_UWS_COMMIT 3ffd6f44c9c3c92c96345d9f96bd01ba9c025ab5)
set(RB_UWS_SHA256 8b51c1457bfd873e44f72f6660d9aef6672eeb1c62739522a242e6904fff8356)
# glaze v9.0.0 (stephenberry/glaze, latest release): glz::route_table, header only, C++23.
set(RB_GLAZE_COMMIT d78832c82289c61a9315bfbc35332cec9f4e93ca)
set(RB_GLAZE_SHA256 72e88f46a96e3cd014fb26af644c540a11811407fb1332fb0a4e068ceec5ba3f)
# cpp-httplib v0.58.0 (yhirose/cpp-httplib, latest release): httplib.h, one header.
set(RB_HTTPLIB_COMMIT 4f3f9ef19be83ae97a5d9a059432dc00e445b7ab)
set(RB_HTTPLIB_SHA256 415e8d638f6e2390f51565d4fdc86577dc0ef09f56da7ea74d7731d9da8349a6)
# chi v5.3.2 (go-chi/chi, latest release; archive
# https://codeload.github.com/go-chi/chi/tar.gz/38939062c5df4d3e8814aad1a488983112627ced, sha256
# 7ff73b6599b96a92a6d1a7db6cb5db33831074224c0d40d3450c26acbab26e97): its package sources
# vendored unchanged in arms/go/chi, each with its sha256 below (checked at configure time,
# cmake/arm-chi.cmake).
set(RB_CHI_TAG v5.3.2)
set(RB_CHI_COMMIT 38939062c5df4d3e8814aad1a488983112627ced)
set(RB_CHI_SHA256_chain_go 8c22d7bbc23f4b4d46ded5ef721a9c3a173031fa2c2c9a7b48c46c2b07e8bd80)
set(RB_CHI_SHA256_chi_go b659c130bc881c5cbaf03080497e3a25e6acbbed7c100ff7d19bf25f9bc64538)
set(RB_CHI_SHA256_context_go bf1f093c84b276cc4790a23014f37abc92f85c0e4f5f6ed4830a233a29628916)
set(RB_CHI_SHA256_mux_go 3255394e5c4f305b47b81e2e3912caaf58455223fe7a126cec5c494c663adb24)
set(RB_CHI_SHA256_tree_go 790a26ead9f2f9bb93e61f2c7ee588096068a26afcf56e115801753bd7ed230c)
# path-tree 0.8.3 (viz-rs/path-tree, latest release): its release archive is the crate published
# on crates.io, the Rust release registry. Cargo.lock (arms/rust) pins it and its one dependency,
# smallvec 1.16.2, by the sha256 of each archive, and Cargo checks the sha256 of every archive it
# uses. The archives, with the sha256 of the copies fetched on 2026-09-30:
#   https://static.crates.io/crates/path-tree/path-tree-0.8.3.crate
#     c2a97453bc21a968f722df730bfe11bd08745cb50d1300b0df2bda131dece136
#   https://static.crates.io/crates/smallvec/smallvec-1.16.2.crate
#     f9395f0f0eee849a9b707b2f06bb92a6a422090e2123bb2ef8e87a0e61892a8e
