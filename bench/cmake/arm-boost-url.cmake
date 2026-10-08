FetchContent_Declare(rb_boost_url_src URL "https://codeload.github.com/boostorg/url/tar.gz/${RB_BOOST_URL_COMMIT}"
                     URL_HASH SHA256=${RB_BOOST_URL_SHA256} SOURCE_SUBDIR no-cmake)
FetchContent_MakeAvailable(rb_boost_url_src)
find_package(Boost 1.92.0 EXACT REQUIRED CONFIG)
set(_url "${rb_boost_url_src_SOURCE_DIR}")
file(GLOB_RECURSE _url_sources CONFIGURE_DEPENDS "${_url}/src/*.cpp")
add_library(rb_boost_url STATIC ${_url_sources} "${_url}/example/router/detail/impl/router.cpp"
            "${_url}/example/router/impl/matches.cpp")
# The pinned Boost.URL headers come before the system's.
target_include_directories(rb_boost_url SYSTEM PUBLIC "${_url}/include" "${_url}/example/router")
target_compile_definitions(rb_boost_url PUBLIC BOOST_URL_NO_LIB=1 BOOST_URL_STATIC_LINK=1 PRIVATE BOOST_URL_SOURCE)
target_link_libraries(rb_boost_url PUBLIC Boost::headers)
rb_arm(boost-url arms/boosturl.cpp rb_boost_url)
