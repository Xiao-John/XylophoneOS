# SPDX-License-Identifier: Apache-2.0
# Native wait primitives are private support routines, not a futex backend.
ifeq ($(subdir),csu)
sysdep_routines += errno-loc
# Use GNU's shared unwind forwards to the already loaded libgcc_s.
routines += unwind-resume
shared-only-routines += unwind-resume
CFLAGS-unwind-resume.c += -fexceptions -fasynchronous-unwind-tables
endif
ifeq ($(subdir),elf)
# GCC's bare-metal driver leaves this to the linker invocation. The shared
# unwinder uses _dl_find_object to locate libc's frame description index.
LDFLAGS.so += -Wl,--eh-frame-hdr
sysdep_routines += cpu-tunables
static-only-routines += cpu-tunables
sysdep-rtld-routines += xos_rtld_entry xos_rtld_mapping xos_file_session xos_rtld_heap xos_rtld_sysdep_start
sysdep-rtld-routines += xos_rtld_sysdep_invoke _exit getpid
sysdep-rtld-routines += xos_rtld_libc_handoff
CFLAGS-dl-load.os += -DXOS_RTLD_CLOSED_DEPENDENCIES
CFLAGS-dl-object.os += -DXOS_RTLD_CLOSED_DEPENDENCIES
CFLAGS-dl-minimal-malloc.os += -DXOS_RTLD_NATIVE_HEAP -ffunction-sections
CFLAGS-rtld.os += -DXOS_RTLD_CLOSED_DEPENDENCIES -ffunction-sections -fdata-sections
CFLAGS-dl-tls.os += -ffunction-sections
CFLAGS-dl-minimal.os += -ffunction-sections
CFLAGS-dl-catch.os += -ffunction-sections
CFLAGS-dl-tunables.os += -ffunction-sections
CFLAGS-dl-mutex.os += -ffunction-sections
CFLAGS-dl-misc.os += -DXOS_RTLD_CLOSED_DEPENDENCIES -ffunction-sections
CFLAGS-xos_rtld_libc_handoff.os += -ffunction-sections
endif
ifeq ($(subdir),dlfcn)
# The first native shared profile exposes a fixed startup closure.
CFLAGS-dlopen.os += -DXOS_DLFUNC_FIXED_CLOSURE
CFLAGS-dlmopen.os += -DXOS_DLFUNC_FIXED_CLOSURE
CFLAGS-dlclose.os += -DXOS_DLFUNC_FIXED_CLOSURE
endif
ifeq ($(subdir),stdlib)
sysdep_routines += xos_process_exit
endif
ifeq ($(subdir),malloc)
# The shared cleanup assumes several optional GNU subdirs are present.
ifeq ($(filter nss,$(subdirs)),)
CFLAGS-set-freeres.os += -DXOS_FREERES_WITHOUT_NSS
endif
ifeq ($(filter resolv,$(subdirs)),)
CFLAGS-set-freeres.os += -DXOS_FREERES_WITHOUT_RESOLV
CFLAGS-thread-freeres.os += -DXOS_FREERES_WITHOUT_RESOLV
endif
ifeq ($(filter inet,$(subdirs)),)
CFLAGS-set-freeres.os += -DXOS_FREERES_WITHOUT_INET
endif
ifeq ($(filter login,$(subdirs)),)
CFLAGS-set-freeres.os += -DXOS_FREERES_WITHOUT_LOGIN
endif
endif
ifeq ($(subdir),posix)
ifeq ($(filter nss,$(subdirs)),)
CPPFLAGS-glob.os += -DXOS_TILDE_WITHOUT_NSS
CPPFLAGS-glob64.os += -DXOS_TILDE_WITHOUT_NSS
CPPFLAGS-wordexp.os += -DXOS_TILDE_WITHOUT_NSS
endif
endif
ifeq ($(subdir),socket)
sysdep_routines += xos_net2_socket
ifeq ($(filter inet,$(subdirs)),)
# Install the public header directly from glibc's inet directory.
sysdep_headers += bits/in.h netinet/in.h netinet/tcp.h
sysdep_routines += htonl htons in6_addr
$(inst_includedir)/netinet/in.h: $(..)inet/netinet/in.h $(+force)
	$(do-install)
$(inst_includedir)/netinet/tcp.h: $(..)sysdeps/gnu/netinet/tcp.h $(+force)
	$(do-install)
endif
ifeq ($(filter resolv,$(subdirs)),)
# The checked address converters use the portable GNU implementations.
sysdep_routines += inet_ntop inet_pton inet_pton_length
shared-only-routines += inet_ntop inet_pton inet_pton_length
endif
endif
ifeq ($(subdir),nptl)
sysdep_headers += bits/pthread_stack_min-dynamic.h bits/pthread_stack_min.h
sysdep_routines += xos_wait_word xos_lll_futex xos_timed_wait xos_thread_exit xos_thread_create xos_thread_tls xos_thread_entry
sysdep_routines += xos_static_worker
sysdep_routines += xos_thread_name xos_nptl_exit
endif

ifeq ($(subdir),io)
sysdep_routines += xos_file_session xos_file_runtime xos_file_positioned xos_anonymous
CFLAGS-xos_file_runtime.os += -ffunction-sections
endif
ifeq ($(subdir),dirent)
sysdep_routines += xos_file_directory
endif
ifeq ($(subdir),termios)
sysdep_routines += xos_terminal_runtime
endif
