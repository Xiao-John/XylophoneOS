/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_D1_ENVIRONMENT_H
#define XOS_D1_ENVIRONMENT_H

/* Both the bootstrap and interpreter use this on bounded, terminated
   environment strings before GNU can process loader controls. */
static inline int
xos_d1_environment_allowed (const char *text)
{
  if (text[0] == 'L' && text[1] == 'D' && text[2] == '_')
    return 0;

  static const char tunables[] = "GLIBC_TUNABLES";
  for (unsigned int i = 0; i < sizeof (tunables) - 1; ++i)
    if (text[i] != tunables[i])
      return 1;
  const char separator = text[sizeof (tunables) - 1];
  return separator != 0 && separator != '=';
}
#endif
