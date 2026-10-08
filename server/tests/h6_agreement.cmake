# The router arms' agreement on the nine H6 cells (design/round2/hypotheses-v2-proposal.md, H6: the
# seven shapes at m = 10, rest and param-last at m = 10,000; the pair (111, 211)), run by CTest:
#     cmake -DH6_TARGETS=... -DAGREE=... -DOUT=DIR -P h6_agreement.cmake
# t1/h6_targets writes each cell's routes and targets; test_agreement checks them.
set(_cells static:10 param-last:10 param-first:10 rest:10 wild:10 mixed-disjoint:10 mixed-overlap:10
           rest:10000 param-last:10000)
file(MAKE_DIRECTORY "${OUT}")
set(_args)
foreach(_c IN LISTS _cells)
    string(REPLACE ":" ";" _p "${_c}")
    list(GET _p 0 _shape)
    list(GET _p 1 _m)
    set(_r "${OUT}/${_shape}-${_m}.routes")
    set(_t "${OUT}/${_shape}-${_m}.targets")
    execute_process(COMMAND "${H6_TARGETS}" --shape ${_shape} --m ${_m} --table-seed 111 --ring-seed 211
                            --routes "${_r}" --targets "${_t}" RESULT_VARIABLE _rc OUTPUT_QUIET)
    if(NOT _rc EQUAL 0)
        message(FATAL_ERROR "h6_targets failed for ${_shape} m=${_m}")
    endif()
    list(APPEND _args "${_r}" "${_t}")
endforeach()
execute_process(COMMAND "${AGREE}" ${_args} RESULT_VARIABLE _rc)
if(NOT _rc EQUAL 0)
    message(FATAL_ERROR "the router arms disagree")
endif()
