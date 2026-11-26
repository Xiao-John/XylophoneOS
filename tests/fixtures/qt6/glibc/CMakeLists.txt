# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.21)
project(qt_glibc_core_fixture LANGUAGES CXX)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "XOS")
    message(FATAL_ERROR "Build this fixture with the XOS glibc Qt toolchain")
endif()

find_package(Qt6 6.8.3 EXACT REQUIRED COMPONENTS Core)
qt_standard_project_setup()
qt_add_executable(core_smoke ../core_smoke.cpp ../resources.qrc)
set_target_properties(core_smoke PROPERTIES AUTORCC ON)
target_link_libraries(core_smoke PRIVATE Qt6::Core)
