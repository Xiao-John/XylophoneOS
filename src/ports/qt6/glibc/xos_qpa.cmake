# SPDX-License-Identifier: Apache-2.0

function(xos_link_qpa target font)
    if(NOT CMAKE_SYSTEM_NAME STREQUAL "XOS" OR NOT XOS_GLIBC_SDK)
        message(FATAL_ERROR "Use the XOS glibc Qt toolchain")
    endif()
    if(NOT EXISTS "${font}")
        message(FATAL_ERROR "The XOS QPA requires its locked QtBase DejaVu font")
    endif()

    get_filename_component(port "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/.." ABSOLUTE)
    set(qpa "${target}_xos_qpa")
    add_library(${qpa} STATIC "${port}/qpa/qxos.cpp")
    set_target_properties(${qpa} PROPERTIES AUTOMOC ON)
    target_compile_definitions(${qpa} PRIVATE QT_STATICPLUGIN)
    target_include_directories(${qpa} PRIVATE "${port}/runtime")
    target_link_libraries(${qpa} PRIVATE Qt6::CorePrivate Qt6::GuiPrivate)

    set_source_files_properties("${font}" PROPERTIES QT_RESOURCE_ALIAS DejaVuSans.ttf)
    qt6_add_resources(${target} xos_fonts PREFIX /xos FILES "${font}")
    target_link_libraries(${target} PRIVATE ${qpa})
    qt6_import_plugins(${target} NO_DEFAULT)
endfunction()
