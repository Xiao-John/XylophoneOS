/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#define __set_errno(value) (errno = (value))
#define libc_hidden_def(name)
#define weak_alias(source, target)
#define __ioctl xos_test_ioctl
