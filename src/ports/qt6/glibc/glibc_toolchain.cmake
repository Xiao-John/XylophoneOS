# SPDX-License-Identifier: Apache-2.0
# Use the admitted XOS glibc SDK even for standalone CMake compiler/link probes.
list(PREPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_LIST_DIR}/../cmake")
set(CMAKE_SYSTEM_NAME XOS)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES
    XOS_GLIBC_SDK XOS_GLIBC_TOOLS XOS_GLIBC_CXX_INCLUDES XOS_SOURCE_ROOT
    XOS_GLIBC_CC XOS_GLIBC_CXX XOS_GLIBC_AR XOS_GLIBC_RANLIB)

set(CMAKE_C_COMPILER "${XOS_GLIBC_CC}")
set(CMAKE_CXX_COMPILER "${XOS_GLIBC_CXX}")
set(CMAKE_AR "${XOS_GLIBC_AR}")
set(CMAKE_RANLIB "${XOS_GLIBC_RANLIB}")
set(CMAKE_ASM_COMPILER "${XOS_GLIBC_CC}")
set(CMAKE_SYSROOT "${XOS_GLIBC_SDK}")
set(CMAKE_FIND_ROOT_PATH "${XOS_GLIBC_SDK}")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

set(lib "${XOS_GLIBC_SDK}/usr/lib")
set(flags "-B\"${XOS_GLIBC_TOOLS}/\" -mno-red-zone -fno-pie -fno-pic -fno-omit-frame-pointer -ftls-model=local-exec -D__XOS__ -D_GNU_SOURCE=1")
set(xos_headers "-I\"${XOS_SOURCE_ROOT}/src/shared/include\" -I\"${XOS_SOURCE_ROOT}/src/user/include\"")
set(sdk_headers "-isystem \"${XOS_GLIBC_SDK}/usr/include\" -isystem \"${lib}/compiler-include\"")
set(cxx_headers "")
foreach(relative IN LISTS XOS_GLIBC_CXX_INCLUDES)
    string(APPEND cxx_headers " -isystem \"${XOS_GLIBC_SDK}/${relative}\"")
endforeach()
set(CMAKE_C_FLAGS_INIT "${flags} -nostdinc ${xos_headers} ${sdk_headers} -DPCRE2_DISABLE_JIT")
set(CMAKE_CXX_FLAGS_INIT "${flags} -nostdinc -nostdinc++ ${xos_headers}${cxx_headers} ${sdk_headers}")
set(CMAKE_ASM_FLAGS_INIT "${CMAKE_C_FLAGS_INIT}")

set(CMAKE_EXE_LINKER_FLAGS_INIT "-static -no-pie -nostdlib -Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096 -T \"${XOS_GLIBC_SDK}/user.ld\" \"${lib}/xos_start.o\" \"${lib}/crti.o\" \"${lib}/crtbegin.o\" \"${lib}/xos_start_c.o\"")
set(libc_group "\"${lib}/libc.a\" \"${lib}/libm.a\" \"${lib}/libxos_terminal.a\" \"${lib}/libgcc.a\"")
set(crt_end "-Wl,--end-group \"${lib}/crtend.o\" \"${lib}/crtn.o\"")
set(CMAKE_C_STANDARD_LIBRARIES_INIT "-Wl,--start-group ${libc_group} ${crt_end}")
set(CMAKE_CXX_STANDARD_LIBRARIES_INIT "-Wl,--start-group \"${lib}/libstdc++.a\" \"${lib}/libsupc++.a\" ${libc_group} ${crt_end}")
