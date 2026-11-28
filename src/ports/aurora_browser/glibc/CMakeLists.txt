# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.21)
project(xos_clarke LANGUAGES C CXX)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "XOS" OR NOT XOS_GLIBC_SDK)
    message(FATAL_ERROR "Use the XOS glibc Qt Widgets toolchain")
endif()

find_package(Qt6 6.8.3 EXACT REQUIRED COMPONENTS Widgets)
set(inputs "")
foreach(module IN ITEMS Core Gui Widgets BundledFreetype BundledHarfbuzz BundledPcre2 BundledZLIB)
    get_target_property(type Qt6::${module} TYPE)
    get_target_property(archive Qt6::${module} IMPORTED_LOCATION_RELEASE)
    set(expected_archive "${XOS_QT_PREFIX}/lib/libQt6${module}.a")
    file(REAL_PATH "${expected_archive}" expected)
    file(REAL_PATH "${archive}" selected)
    if(NOT type STREQUAL "STATIC_LIBRARY" OR NOT selected STREQUAL expected
            OR NOT EXISTS "${expected_archive}")
        message(FATAL_ERROR "ClarkE requires the installed Qt6::${module} archive from XOS_QT_PREFIX")
    endif()
    string(APPEND inputs "${module}=${selected}\n")
endforeach()
string(APPEND inputs "moc=$<TARGET_FILE:Qt6::moc>\nrcc=$<TARGET_FILE:Qt6::rcc>\n")
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/qt_inputs.txt" CONTENT "${inputs}")

set(BUILD_SHARED_LIBS OFF)
set(LITEHTML_BUILD_TESTING OFF CACHE BOOL "")
set(EXTERNAL_GUMBO OFF CACHE BOOL "")
add_subdirectory("${XOS_CLARKE_LITEHTML_SOURCE}" litehtml EXCLUDE_FROM_ALL)
target_compile_features(litehtml PRIVATE cxx_std_17)

set(qt_port "${CMAKE_CURRENT_LIST_DIR}/../../qt6")
set(aurora "${qt_port}/aurora")
add_library(clarke_aurora STATIC
    "${aurora}/style.cpp"
    "${aurora}/theme.cpp"
    "${aurora}/blur.cpp"
    "${aurora}/semantics.cpp"
    "${aurora}/ssg.cpp"
)
target_compile_features(clarke_aurora PUBLIC cxx_std_17)
target_link_libraries(clarke_aurora PUBLIC Qt6::Widgets)

qt6_add_executable(clarke ../main.cpp ../../browser_http/http.cpp ../../browser_http/transport.cpp)
target_compile_features(clarke PRIVATE cxx_std_17)
qt6_add_resources(clarke xos_aurora PREFIX /xos BASE "${aurora}/assets"
    FILES "${aurora}/assets/aurora.bmp")
target_link_libraries(clarke PRIVATE clarke_aurora litehtml)
set_target_properties(clarke PROPERTIES SUFFIX ".elf")

if(XOS_CLARKE_TLS_BUILD)
    set(tls "${CMAKE_CURRENT_LIST_DIR}/../../native_tls")
    set(psa "${XOS_CLARKE_TLS_UPSTREAM}/tf-psa-crypto")
    target_sources(clarke PRIVATE https.cpp ../../browser_http/https_transport.cpp
        "${tls}/stream.cpp" "${tls}/trust_store.cpp" "${tls}/platform.c")
    target_compile_features(clarke PRIVATE c_std_11)
    target_compile_definitions(clarke PRIVATE
        XOS_CLARKE_HTTPS=1
        MBEDTLS_USER_CONFIG_FILE="${tls}/mbedtls_xos_config.h"
        TF_PSA_CRYPTO_USER_CONFIG_FILE="${tls}/tf_psa_crypto_xos_config.h")
    target_include_directories(clarke PRIVATE
        "${XOS_CLARKE_TLS_CONFIG}" "${XOS_CLARKE_TLS_UPSTREAM}/include"
        "${psa}/include" "${psa}/drivers/builtin/include")
    target_link_libraries(clarke PRIVATE
        "${XOS_CLARKE_TLS_BUILD}/mbedtls/library/libmbedtls.a"
        "${XOS_CLARKE_TLS_BUILD}/mbedtls/library/libmbedx509.a"
        "${XOS_CLARKE_TLS_BUILD}/mbedtls/tf-psa-crypto/core/libtfpsacrypto.a")
endif()

include("${qt_port}/glibc/xos_qpa.cmake")
xos_link_qpa(clarke "${XOS_QTBASE_SOURCE}/src/3rdparty/wasm/DejaVuSans.ttf")
