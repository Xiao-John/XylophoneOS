/* SPDX-License-Identifier: Apache-2.0
   Candidate XOS glibc waitid selector values.  Defining a selector does not
   imply that the corresponding waitid operation is implemented.  */
#ifndef __idtype_t_defined
#define __idtype_t_defined 1
typedef enum
{
  P_ALL = 0,
  P_PID = 1,
  P_PGID = 2
} idtype_t;
#endif
