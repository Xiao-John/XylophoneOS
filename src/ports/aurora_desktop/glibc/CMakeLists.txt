# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.21)
project(xos_mobius LANGUAGES CXX)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "XOS" OR NOT XOS_GLIBC_SDK)
    message(FATAL_ERROR "Use the XOS glibc Qt Widgets toolchain")
endif()

find_package(Qt6 6.8.3 EXACT REQUIRED COMPONENTS Widgets)
if(NOT IS_DIRECTORY "${XOS_QT_PREFIX}")
    message(FATAL_ERROR "Specify the installed Qt Widgets build with XOS_QT_PREFIX")
endif()

set(inputs "")
foreach(module IN ITEMS Core Gui Widgets BundledFreetype BundledHarfbuzz BundledPcre2 BundledZLIB)
    get_target_property(type Qt6::${module} TYPE)
    get_target_property(archive Qt6::${module} IMPORTED_LOCATION_RELEASE)
    set(expected_archive "${XOS_QT_PREFIX}/lib/libQt6${module}.a")
    file(REAL_PATH "${expected_archive}" expected)
    file(REAL_PATH "${archive}" selected)
    if(NOT type STREQUAL "STATIC_LIBRARY" OR NOT selected STREQUAL expected
            OR NOT EXISTS "${expected_archive}")
        message(FATAL_ERROR "Mobius requires the installed Qt6::${module} archive from XOS_QT_PREFIX")
    endif()
    string(APPEND inputs "${module}=${selected}\n")
endforeach()
string(APPEND inputs "moc=$<TARGET_FILE:Qt6::moc>\nrcc=$<TARGET_FILE:Qt6::rcc>\n")
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/qt_inputs.txt" CONTENT "${inputs}")

set(qt_port "${CMAKE_CURRENT_LIST_DIR}/../../qt6")
set(aurora "${qt_port}/aurora")
add_library(mobius_aurora STATIC
    "${aurora}/style.cpp"
    "${aurora}/theme.cpp"
    "${aurora}/blur.cpp"
    "${aurora}/semantics.cpp"
    "${aurora}/ssg.cpp"
)
target_compile_features(mobius_aurora PUBLIC cxx_std_17)
target_link_libraries(mobius_aurora PUBLIC Qt6::Widgets)

qt6_add_executable(mobius ../main.cpp)
qt6_add_resources(mobius xos_aurora PREFIX /xos BASE "${aurora}/assets"
    FILES "${aurora}/assets/aurora.bmp")
set(wallpaper "${aurora}/assets/curvive_wallpaper.bmp")
set_source_files_properties("${wallpaper}" PROPERTIES QT_RESOURCE_ALIAS aurora-wallpaper.bmp)
qt6_add_resources(mobius mobius_wallpaper PREFIX /xos FILES "${wallpaper}")
target_link_libraries(mobius PRIVATE mobius_aurora)

include("${qt_port}/glibc/xos_qpa.cmake")
if(NOT XOS_MOBIUS_FONT)
    set(XOS_MOBIUS_FONT "${XOS_QTBASE_SOURCE}/src/3rdparty/wasm/DejaVuSans.ttf")
endif()
xos_link_qpa(mobius "${XOS_MOBIUS_FONT}")

set(user_source "${XOS_SOURCE_ROOT}/src/user")
set(loader_sources
    "${user_source}/loader/elf.cpp"
    "${user_source}/loader/load.cpp"
    "${user_source}/sdk/file_client.cpp"
    "${user_source}/sdk/text.cpp"
    "${user_source}/arch/x86_64/tls.cpp"
)
set_source_files_properties(${loader_sources} PROPERTIES COMPILE_OPTIONS "-ffreestanding;-fno-exceptions;-fno-rtti")
add_executable(mobius_session ../session.cpp ${loader_sources})
target_compile_features(mobius_session PRIVATE cxx_std_17)
# Keep the loader and libc on the same file-service session.
target_link_options(mobius_session PRIVATE "LINKER:--require-defined=xos_file_session_exchange")
file(WRITE "${CMAKE_BINARY_DIR}/loader_sources.txt" "${loader_sources}")
