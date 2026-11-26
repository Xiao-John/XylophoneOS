# SPDX-License-Identifier: Apache-2.0
# Native wait primitives are private support routines, not a futex backend.
ifeq ($(subdir),csu)
sysdep_routines += errno-loc
endif
ifeq ($(subdir),elf)
sysdep_routines += cpu-tunables
sysdep-rtld-routines += xos_rtld_entry xos_rtld_mapping xos_file_session
CFLAGS-dl-load.os += -DXOS_RTLD_CLOSED_DEPENDENCIES
endif
ifeq ($(subdir),stdlib)
sysdep_routines += xos_process_exit
endif
ifeq ($(subdir),nptl)
sysdep_headers += bits/pthread_stack_min-dynamic.h bits/pthread_stack_min.h
sysdep_routines += xos_wait_word xos_lll_futex xos_timed_wait xos_thread_exit xos_thread_create xos_thread_tls xos_thread_entry
static-only-routines += xos_static_worker
sysdep_routines += xos_static_worker
sysdep_routines += xos_thread_name xos_nptl_exit
endif

ifeq ($(subdir),io)
sysdep_routines += xos_file_session xos_file_runtime xos_file_positioned xos_anonymous
endif
ifeq ($(subdir),dirent)
sysdep_routines += xos_file_directory
endif
ifeq ($(subdir),termios)
sysdep_routines += xos_terminal_runtime
endif
