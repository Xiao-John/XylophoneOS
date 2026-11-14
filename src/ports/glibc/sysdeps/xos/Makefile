# SPDX-License-Identifier: Apache-2.0
# Native wait primitives are private support routines, not a futex backend.
ifeq ($(subdir),nptl)
sysdep_routines += xos_wait_word xos_lll_futex xos_timed_wait xos_thread_exit xos_thread_create xos_thread_tls
endif
