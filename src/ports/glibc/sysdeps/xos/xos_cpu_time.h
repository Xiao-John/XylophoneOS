/* SPDX-License-Identifier: Apache-2.0
   Private C representation of XOS process_cpu_time v1.  */
#ifndef XOS_GLIBC_CPU_TIME_H
#define XOS_GLIBC_CPU_TIME_H 1
struct xos_cpu_time {
  __UINT32_TYPE__ version, size;
  __UINT64_TYPE__ user_ns, system_ns, child_user_ns, child_system_ns;
  __UINT64_TYPE__ thread_user_ns, thread_system_ns, elapsed_ns, resolution_ns;
};
#endif
