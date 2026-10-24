# SPDX-License-Identifier: Apache-2.0
# Cross-configure answers grounded in the E08-2 runtime contract.
# Do not turn absent APIs into success stubs.
ac_cv_func_fork=no
ac_cv_func_vfork=no
ac_cv_func_mmap=no
ac_cv_func_lstat=no
ac_cv_func_access=yes
ac_cv_func_sysconf=yes
ac_cv_func_gettimeofday=yes
ac_cv_func_mkstemp=yes
ac_cv_func_mkstemps=yes
ac_cv_func_popen=no
ac_cv_func_dlopen=no
ac_cv_func_dlsym=no
ac_cv_func_dlclose=no
ac_cv_tls=none
