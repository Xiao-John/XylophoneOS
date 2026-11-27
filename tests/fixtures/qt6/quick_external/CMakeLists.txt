# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.21)
project(xos_quick_file_probe LANGUAGES CXX)

find_package(Qt6 6.8.3 EXACT REQUIRED COMPONENTS Core Gui Qml Quick)
qt_add_executable(quick_file_probe main.cpp)
include("${XOS_QUICK_SUPPORT}")
xos_link_quick_app(quick_file_probe)
target_link_libraries(quick_file_probe PRIVATE Qt6::qtquick2plugin Qt6::qmlplugin
                                              Qt6::modelsplugin Qt6::quickwindow)
