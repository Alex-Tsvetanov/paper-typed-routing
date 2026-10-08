# Oat++ declares cmake_minimum_required(3.1), which CMake 4 refuses without a policy floor.
set(OATPP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(OATPP_INSTALL OFF CACHE BOOL "" FORCE)
set(OATPP_LINK_TEST_LIBRARY OFF CACHE BOOL "" FORCE)
# Oat++ 1.3.1's CMakeLists.txt, line 38: option(OATPP_DISABLE_ENV_OBJECT_COUNTERS "Disable object
# counting for Release builds for better performance" OFF), its documented release setting. It
# removes an atomic count from every oatpp::base::Countable's constructor and destructor
# (src/oatpp/core/base/Countable.cpp); only Oat++'s .cpp files read it, so the adapter needs no define.
set(OATPP_DISABLE_ENV_OBJECT_COUNTERS ON CACHE BOOL "" FORCE)
set(CMAKE_POLICY_VERSION_MINIMUM 3.5)
FetchContent_Declare(rb_oatpp_src URL "https://codeload.github.com/oatpp/oatpp/tar.gz/${RB_OATPP_COMMIT}"
                     URL_HASH SHA256=${RB_OATPP_SHA256})
FetchContent_MakeAvailable(rb_oatpp_src)
unset(CMAKE_POLICY_VERSION_MINIMUM)
rb_arm(oatpp arms/oatpp.cpp oatpp)
