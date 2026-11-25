/* SPDX-License-Identifier: Apache-2.0
   XOS does not use the Linux cancellable-syscall assembly trampoline.
   The native unsupported-operation paths live in cancellation.c.  This
   translation unit satisfies NPTL's architecture-object rule without
   issuing a host or Linux target syscall.  */
