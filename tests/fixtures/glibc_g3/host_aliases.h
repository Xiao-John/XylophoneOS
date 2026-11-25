/* SPDX-License-Identifier: Apache-2.0
   Compile production writev under a private name without interposing host libc. */
#include <errno.h>
#define __set_errno(value) (errno = (value))
#define libc_hidden_def(name)
#define weak_alias(source, target)
#define __writev xos_test_writev
