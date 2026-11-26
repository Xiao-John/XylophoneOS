# SPDX-License-Identifier: Apache-2.0

function(xos_link_quick_app target)
    if(NOT CMAKE_SYSTEM_NAME STREQUAL "XOS" OR NOT XOS_GLIBC_SDK)
        message(FATAL_ERROR "Use the XOS glibc Qt Quick application builder")
    endif()
    if(NOT Qt6_VERSION VERSION_EQUAL XOS_QUICK_QT_VERSION)
        message(FATAL_ERROR "Use target Qt ${XOS_QUICK_QT_VERSION} for the XOS Quick application")
    endif()

    set(inputs "")
    foreach(module IN ITEMS Core Gui Qml QmlMeta QmlModels Quick
            BundledPcre2 BundledZLIB BundledFreetype BundledHarfbuzz
            qtquick2plugin qmlplugin modelsplugin quickwindow)
        get_target_property(module_type Qt6::${module} TYPE)
        if(NOT module_type STREQUAL "STATIC_LIBRARY")
            message(FATAL_ERROR "XOS Qt Quick requires static Qt6::${module}")
        endif()
        string(APPEND inputs "${module}=$<TARGET_FILE:Qt6::${module}>\n")
    endforeach()
    foreach(tool IN ITEMS moc rcc qmlimportscanner qmltyperegistrar qmlcachegen)
        string(APPEND inputs "${tool}=$<TARGET_FILE:Qt6::${tool}>\n")
    endforeach()
    file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/${target}-qt-inputs.txt" CONTENT "${inputs}")

    get_filename_component(port "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/.." ABSOLUTE)
    set(qpa "${target}_xos_qpa")
    add_library(${qpa} STATIC "${port}/qpa/qxos.cpp")
    set_target_properties(${qpa} PROPERTIES AUTOMOC ON)
    target_compile_definitions(${qpa} PRIVATE QT_STATICPLUGIN)
    target_include_directories(${qpa} PRIVATE "${port}/runtime")
    target_link_libraries(${qpa} PRIVATE Qt6::CorePrivate Qt6::GuiPrivate)

    set_source_files_properties("${XOS_QTBASE_FONT}" PROPERTIES QT_RESOURCE_ALIAS DejaVuSans.ttf)
    qt6_add_resources(${target} xos_fonts PREFIX /xos FILES "${XOS_QTBASE_FONT}")
    target_link_libraries(${target} PRIVATE Qt6::Quick ${qpa})
    qt6_import_plugins(${target} NO_DEFAULT)
endfunction()
