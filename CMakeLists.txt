cmake_minimum_required(VERSION 3.24)
project(asmc VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/bin")

# Upstream tips resolved on 2026-10-13. Override these cache values to update.
include(FetchContent)
set(FETCHCONTENT_UPDATES_DISCONNECTED ON)
set(ASMC_CBMC_REV "32441ee38f8b2be63281a88a0df1a585dd4fdc43" CACHE STRING "CBMC commit")
set(ASMC_SLEIGH_REV "bfe2771eb304c2b4f01c2fa61f5342be54a91906" CACHE STRING "SLEIGH commit")
set(enable_cbmc_tests OFF CACHE BOOL "" FORCE)
set(WITH_JBMC OFF CACHE BOOL "" FORCE)
set(WITH_MEMORY_ANALYZER OFF CACHE BOOL "" FORCE)
set(sleigh_BUILD_TOOLS ON CACHE BOOL "" FORCE)
set(sleigh_BUILD_SLEIGHSPECS ON CACHE BOOL "" FORCE)
set(sleigh_BUILD_SUPPORT OFF CACHE BOOL "" FORCE)
set(sleigh_BUILD_EXTRATOOLS OFF CACHE BOOL "" FORCE)
set(CMAKE_SKIP_INSTALL_RULES TRUE)
FetchContent_Declare(cbmc URL "https://github.com/diffblue/cbmc/archive/${ASMC_CBMC_REV}.tar.gz")
FetchContent_Declare(sleigh URL "https://github.com/lifting-bits/sleigh/archive/${ASMC_SLEIGH_REV}.tar.gz")
FetchContent_MakeAvailable(cbmc sleigh)
set(ASMC_SPEC_DIR "${sleigh_BINARY_DIR}/specfiles/Ghidra/Processors")
add_library(asmc-core src/elf_image.cpp src/lifter.cpp src/pcode_expr.cpp src/translate.cpp)
target_include_directories(asmc-core PUBLIC src PRIVATE vendor/elfio)
target_link_libraries(asmc-core PUBLIC sleigh::sla goto-programs)
target_compile_options(asmc-core PRIVATE -Wall -Wextra -Wno-unused-parameter)
add_executable(asmc-lift src/lift_main.cpp)
target_link_libraries(asmc-lift PRIVATE asmc-core)
target_compile_definitions(asmc-lift PRIVATE ASMC_SPEC_DIR="${ASMC_SPEC_DIR}")
add_dependencies(asmc-lift sleigh_spec_x86-64 sleigh_spec_riscv_ilp32d sleigh_spec_riscv_lp64d)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
configure_file(tools/asmc.in "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/asmc" @ONLY
  FILE_PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)
add_custom_target(asmc ALL DEPENDS asmc-lift cbmc goto-cc "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/asmc")
add_custom_target(asmc-tools DEPENDS asmc goto-instrument)
add_executable(asmc-semantics tests/semantics.cpp)
target_link_libraries(asmc-semantics PRIVATE asmc-core solvers)
add_dependencies(asmc-tools asmc-semantics)

enable_testing()
add_test(NAME asmc-semantics COMMAND asmc-semantics)
set_tests_properties(asmc-semantics PROPERTIES LABELS fast)

# Pytest owns case discovery and fast/slow markers; CTest remains the build entry point.
foreach(suite fast slow)
  add_test(NAME asmc-${suite} COMMAND ${Python3_EXECUTABLE} -m pytest -q
    ${CMAKE_CURRENT_SOURCE_DIR}/tests -m ${suite}
    --build-dir ${CMAKE_CURRENT_BINARY_DIR}
    --basetemp ${CMAKE_CURRENT_BINARY_DIR}/pytest-${suite}
    --junitxml ${CMAKE_CURRENT_BINARY_DIR}/pytest-${suite}.xml)
  set_tests_properties(asmc-${suite} PROPERTIES LABELS ${suite})
endforeach()
set_tests_properties(asmc-fast PROPERTIES TIMEOUT 300)
set_tests_properties(asmc-slow PROPERTIES TIMEOUT 2400)

# Repeat the same semantic/oracle cases under the alternative register encoding.
set(scalar_suites challenges demo calls objects native riscv_native switch riscv compose cbat scalar)
set(scalar_tests)
foreach(suite IN LISTS scalar_suites)
  list(APPEND scalar_tests ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_${suite}.py)
endforeach()
add_test(NAME asmc-scalar-registers COMMAND ${Python3_EXECUTABLE} -m pytest -q
  ${scalar_tests} --scalar-registers --build-dir ${CMAKE_CURRENT_BINARY_DIR}
  --basetemp ${CMAKE_CURRENT_BINARY_DIR}/pytest-scalar
  --junitxml ${CMAKE_CURRENT_BINARY_DIR}/pytest-scalar.xml)
set_tests_properties(asmc-scalar-registers PROPERTIES LABELS slow TIMEOUT 1800 RUN_SERIAL TRUE)
