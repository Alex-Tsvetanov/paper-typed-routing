# v2's C interface on round 3's request sets, run by CTest:
#     cmake -DE2E=... -DTEST=... -DOUT=DIR -P p2v2_cells.cmake
# t3/e2e_requests writes four cells (both shapes at m = 10 and 1,000, the pair (111, 211), every
# route and the T0 ring), and test_p2v2 checks every answer of each (tests/test_p2v2.cpp).
set(_cells mixed-disjoint:10 mixed-disjoint:1000 static:10 static:1000)
set(_dirs)
foreach(_c IN LISTS _cells)
    string(REPLACE ":" ";" _p "${_c}")
    list(GET _p 0 _shape)
    list(GET _p 1 _m)
    set(_d "${OUT}/${_shape}-${_m}")
    file(MAKE_DIRECTORY "${_d}")
    execute_process(COMMAND "${E2E}" --shape ${_shape} --m ${_m} --table-seed 111 --ring-seed 211 --out "${_d}"
                    RESULT_VARIABLE _rc OUTPUT_QUIET)
    if(NOT _rc EQUAL 0)
        message(FATAL_ERROR "e2e_requests failed for ${_shape} m=${_m}")
    endif()
    list(APPEND _dirs "${_d}")
endforeach()
execute_process(COMMAND "${TEST}" ${_dirs} RESULT_VARIABLE _rc)
if(NOT _rc EQUAL 0)
    message(FATAL_ERROR "test_p2v2 failed")
endif()
