# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.21)
project(xos_quick_probe LANGUAGES CXX)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "XOS")
    message(FATAL_ERROR "Use the XOS glibc Qt Quick toolchain")
endif()

find_package(Qt6 6.8.3 EXACT REQUIRED COMPONENTS Core Gui Qml Quick)

if(DEFINED XOS_QUICK_SUPPORT)
    qt_standard_project_setup(REQUIRES 6.8)
    qt_add_executable(quick_probe main.cpp)
    qt_add_qml_module(quick_probe URI Xos.QuickLifecycle VERSION 1.0
                      RESOURCE_PREFIX /quick NO_RESOURCE_TARGET_PATH QML_FILES scene.qml)
    include("${XOS_QUICK_SUPPORT}")
    xos_link_quick_app(quick_probe)
    return()
endif()

qt_standard_project_setup()
set(qt_archives "")
foreach(module IN ITEMS Core Gui Qml Quick)
    get_target_property(module_type Qt6::${module} TYPE)
    if(NOT module_type STREQUAL "STATIC_LIBRARY")
        message(FATAL_ERROR "The software scene requires static Qt6::${module}")
    endif()
    string(APPEND qt_archives "$<TARGET_FILE:Qt6::${module}>\n")
endforeach()
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/qt_archives.txt" CONTENT "${qt_archives}")

get_filename_component(xos_root "${CMAKE_CURRENT_LIST_DIR}/../../../.." ABSOLUTE)
set(port "${xos_root}/src/ports/qt6")
add_library(xos_quick_qpa STATIC "${port}/qpa/qxos.cpp")
target_compile_definitions(xos_quick_qpa PRIVATE QT_STATICPLUGIN)
target_include_directories(xos_quick_qpa PRIVATE "${port}/runtime")
target_link_libraries(xos_quick_qpa PRIVATE Qt6::CorePrivate Qt6::GuiPrivate)

if(NOT EXISTS "${XOS_QTBASE_SOURCE}/src/3rdparty/wasm/DejaVuSans.ttf")
    message(FATAL_ERROR "The font must come from the locked QtBase source tree")
endif()
set(font "${XOS_QTBASE_SOURCE}/src/3rdparty/wasm/DejaVuSans.ttf")
set_source_files_properties("${font}" PROPERTIES QT_RESOURCE_ALIAS DejaVuSans.ttf)

qt_add_executable(quick_probe main.cpp)
qt_add_resources(quick_probe quick_scene PREFIX /quick FILES scene.qml)
qt_add_resources(quick_probe xos_fonts PREFIX /xos FILES "${font}")
target_link_libraries(quick_probe PRIVATE Qt6::Quick xos_quick_qpa)
qt_import_plugins(quick_probe NO_DEFAULT)
