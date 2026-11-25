/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_terminal_runtime.h"
#include "xos_file_runtime.h"
#include <errno.h>
#include <string.h>

static long
lease_terminal (int fd, struct xos_file_lease *lease)
{
  long result = __xos_file_lease_acquire (fd, -1, lease);
  if (result < 0) return result;
  if (lease->kind == xos_file_kind_terminal) return 0;
  (void) __xos_file_lease_release (lease);
  return -ENOTTY;
}

long
__xos_terminal_tcgetattr (int fd, struct termios *output)
{
  if (output == NULL) return -EFAULT;
  struct xos_file_lease lease;
  long result = lease_terminal (fd, &lease);
  if (result < 0) return result;
  struct xos_terminal_mode mode;
  result = __xos_terminal_get_mode (&mode);
  if (result == 0)
    {
      struct termios value;
      memset (&value, 0, sizeof (value));
      value.c_cflag = CS8 | CREAD | CLOCAL;
      value.c_ispeed = value.c_ospeed = B115200;
      value.c_cc[VMIN] = (cc_t) mode.vmin;
      value.c_cc[VTIME] = (cc_t) mode.vtime;
      *output = value;
    }
  (void) __xos_file_lease_release (&lease);
  return result;
}

long
__xos_terminal_tcsetattr (int fd, int action, const struct termios *value)
{
  if (value == NULL) return -EFAULT;
  struct xos_file_lease lease;
  long result = lease_terminal (fd, &lease);
  if (result < 0) return result;
  if (action != TCSANOW && action != TCSADRAIN && action != TCSAFLUSH)
    result = -EINVAL;
  else if (value->c_iflag != 0 || value->c_oflag != 0 || value->c_lflag != 0
           || value->c_cflag != (CS8 | CREAD | CLOCAL)
           || value->c_ispeed != B115200 || value->c_ospeed != B115200)
    result = -ENOTSUP;
  else
    {
      for (unsigned int i = 0; i < NCCS; ++i)
        if (i != VMIN && i != VTIME && value->c_cc[i] != 0) result = -ENOTSUP;
      if (result == 0)
        {
          const struct xos_terminal_mode mode =
            { 0, 0, 0, 0, 115200, 115200, value->c_cc[VMIN], value->c_cc[VTIME] };
          const unsigned int native_action = action == TCSANOW ? 0
            : action == TCSADRAIN ? 1 : 2;
          result = __xos_terminal_set_mode (&mode, native_action);
        }
    }
  (void) __xos_file_lease_release (&lease);
  return result;
}

long
__xos_terminal_tcdrain (int fd)
{
  struct xos_file_lease lease;
  long result = lease_terminal (fd, &lease);
  if (result < 0) return result;
  result = __xos_terminal_drain ();
  (void) __xos_file_lease_release (&lease);
  return result;
}

long
__xos_terminal_tcflush (int fd, int queue)
{
  struct xos_file_lease lease;
  long result = lease_terminal (fd, &lease);
  if (result < 0) return result;
  if (queue != TCIFLUSH && queue != TCOFLUSH && queue != TCIOFLUSH) result = -EINVAL;
  else if (queue != TCIFLUSH) result = -ENOTSUP;
  else result = __xos_terminal_flush_input ();
  (void) __xos_file_lease_release (&lease);
  return result;
}
