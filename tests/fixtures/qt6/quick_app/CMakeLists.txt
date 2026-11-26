# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.21)
project(xos_quick_app LANGUAGES CXX)

find_package(Qt6 6.8.3 EXACT REQUIRED COMPONENTS Quick)
qt_standard_project_setup(REQUIRES 6.8)

qt_add_executable(quick_app main.cpp)
qt_add_qml_module(quick_app
    URI Xos.QuickExample
    VERSION 1.0
    QML_FILES Main.qml
)

include("${XOS_QUICK_SUPPORT}")
xos_link_quick_app(quick_app)
