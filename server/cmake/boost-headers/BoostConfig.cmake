# find_package(Boost CONFIG) for a Boost header tree that has no CMake package: the laptop's Windows
# has Boost 1.92.0 as the unpacked boost-1.92.0-b2-nodocs.zip (STATE.md, Laptop request 1), headers
# only. server/CMakeLists.txt points Boost_DIR here when P2_BOOST_ROOT names that tree, so round 2's
# bench/cmake/arm-boost-url.cmake finds Boost::headers unchanged. BoostConfigVersion.cmake reads the
# version from boost/version.hpp. BOOST_ALL_NO_LIB turns off Boost's automatic linking on Windows:
# the boost-url arm compiles Boost.URL's sources itself and links no Boost library.
if(NOT EXISTS "${P2_BOOST_ROOT}/boost/version.hpp")
    set(Boost_FOUND FALSE)
    set(Boost_NOT_FOUND_MESSAGE "P2_BOOST_ROOT=${P2_BOOST_ROOT} has no boost/version.hpp")
    return()
endif()
if(NOT TARGET Boost::headers)
    add_library(Boost::headers INTERFACE IMPORTED)
    set_target_properties(Boost::headers PROPERTIES INTERFACE_INCLUDE_DIRECTORIES "${P2_BOOST_ROOT}"
                                                    INTERFACE_COMPILE_DEFINITIONS BOOST_ALL_NO_LIB)
endif()
set(Boost_INCLUDE_DIRS "${P2_BOOST_ROOT}")
set(Boost_FOUND TRUE)
