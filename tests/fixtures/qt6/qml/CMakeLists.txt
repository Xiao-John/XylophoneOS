# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.21)
project(qml_probe LANGUAGES CXX)

find_package(Qt6 6.8.3 EXACT REQUIRED COMPONENTS Core Qml)
qt_standard_project_setup()
get_target_property(qt_core_type Qt6::Core TYPE)
get_target_property(qt_qml_type Qt6::Qml TYPE)
if(NOT qt_core_type STREQUAL "STATIC_LIBRARY" OR NOT qt_qml_type STREQUAL "STATIC_LIBRARY")
    message(FATAL_ERROR "The E18 fixture requires static QtCore and QtQml")
endif()

qt_add_qml_module(probe_types
    STATIC
    URI Xos.QmlProbe
    VERSION 1.0
    RESOURCE_PREFIX /qt/qml
    OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/Xos/QmlProbe
    NO_CACHEGEN
    QML_FILES Counter.qml
)

qt_add_executable(qml_probe main.cpp)
qt_add_resources(qml_probe qml_probe_resources
    PREFIX /e18
    FILES entry.qml
)
target_link_libraries(qml_probe PRIVATE Qt6::Qml probe_typesplugin)

if(CMAKE_SYSTEM_NAME STREQUAL "XOS")
    add_executable(qml_quota_probe quota.cpp)
    target_link_libraries(qml_quota_probe PRIVATE Qt6::Qml)
endif()
