# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.21)
project(xos_webcore_xml_discovery LANGUAGES NONE)

set(CMAKE_PREFIX_PATH "${XOS_XML_PREFIX}")
set(CMAKE_FIND_ROOT_PATH "${XOS_XML_PREFIX}")
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
set(ENV{PKG_CONFIG_PATH} "")
set(ENV{PKG_CONFIG_LIBDIR} "${XOS_XML_PREFIX}/lib/pkgconfig")
set(ENV{PKG_CONFIG_SYSROOT_DIR} "")
find_package(LibXml2 2.9.13 MODULE REQUIRED)

get_target_property(xml_archive LibXml2::LibXml2 IMPORTED_LOCATION)
get_target_property(xml_headers LibXml2::LibXml2 INTERFACE_INCLUDE_DIRECTORIES)
cmake_path(SET expected_archive NORMALIZE "${XOS_XML_PREFIX}/lib/libxml2.a")
cmake_path(SET expected_headers NORMALIZE "${XOS_XML_PREFIX}/include/libxml2")
if(NOT "${xml_archive}" STREQUAL "${expected_archive}" OR
   NOT "${xml_headers}" STREQUAL "${expected_headers}")
    message(FATAL_ERROR "LibXml2 resolved outside the verified XOS target prefix")
endif()
file(WRITE "${CMAKE_BINARY_DIR}/target-version.txt" "${LIBXML2_VERSION_STRING}\n")
