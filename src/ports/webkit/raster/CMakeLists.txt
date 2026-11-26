# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.21)
project(xos_skia_raster_probe LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ZLIB REQUIRED)
find_package(PNG REQUIRED)
find_package(JPEG REQUIRED)
find_package(Freetype 2.9.0 REQUIRED)
include("${XOS_SKIA_SOURCES}")
add_library(skia_raster STATIC ${skia_sources})
target_include_directories(skia_raster PUBLIC "${XOS_SKIA_SOURCE}")
target_link_libraries(skia_raster PUBLIC PNG::PNG JPEG::JPEG Freetype::Freetype)
target_compile_definitions(skia_raster PRIVATE SKIA_IMPLEMENTATION=1 SK_CODEC_DECODES_PNG
    SK_GAMMA_APPLY_TO_A8 SK_RELEASE SK_DISABLE_LEGACY_INIT_DECODERS SK_DISABLE_TRACING
    SK_DISABLE_LEGACY_GL_MAKE_NATIVE_INTERFACE SK_DISABLE_LEGACY_IMAGE_READBUFFER SK_DISABLE_LEGACY_PNG_WRITEBUFFER
    SK_DISABLE_WEBGL_INTERFACE SK_TYPEFACE_FACTORY_FREETYPE SK_OPTIMIZE_SIZE SKCMS_DISABLE_HSW SKCMS_DISABLE_SKX
    SK_USER_CONFIG_HEADER=\"./WebKitSkiaConfig.h\")
target_compile_definitions(skia_raster PUBLIC SK_BUILD_FOR_UNIX SK_ASSUME_GL=0 SK_ASSUME_GL_ES=0 SK_ASSUME_WEBGL=0)
target_compile_options(skia_raster PRIVATE -O1 -ffp-contract=off -ffunction-sections -fdata-sections
    "--param=ggc-min-expand=10" "--param=ggc-min-heapsize=8192")

add_executable(skia_raster_probe raster_probe.cpp)
target_link_libraries(skia_raster_probe PRIVATE skia_raster)

add_executable(skia_file_stream_probe file_stream_probe.cpp)
target_link_libraries(skia_file_stream_probe PRIVATE skia_raster)
