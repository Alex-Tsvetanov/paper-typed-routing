// The server's stand-in for rbench's core/runner.hpp (design/round3/end-to-end.md, section 6).
//
// Round 2's adapters (bench/arms/*.cpp) include "core/runner.hpp" and end with RB_ARM(Type). The
// server compiles them unchanged with this directory ahead of bench/ on the include path, so their
// include finds this file. It gives them the arm contract (bench/core/arm.hpp, unchanged) and turns
// RB_ARM(Type) into a registration of Type as a router arm of the server (external.hpp). Nothing of
// the harness's measurement code is compiled into the server.
#pragma once

#include "core/arm.hpp"
#include "external.hpp"

#define RB_ARM(Type)                                                                                      \
    namespace {                                                                                          \
    [[maybe_unused]] const bool mserver_registered_arm =                                                 \
        ::mserver::register_external(Type::info().name, Type::info().version, &::mserver::make_external<Type>); \
    }
