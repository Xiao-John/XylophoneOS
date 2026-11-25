/* SPDX-License-Identifier: Apache-2.0
   Convert the XOS thread_start register state to an x86-64 C call.  */
#include <xos_thread_entry.h>

	.text
	.p2align 4
	.globl __xos_thread_entry
	.hidden __xos_thread_entry
	.type __xos_thread_entry,@function
__xos_thread_entry:
	.cfi_startproc
	.cfi_undefined %rip
	/* The kernel enters with RSP aligned to 16 and RDI pointing to the
	   record.  CALL pushes the return address required by the C ABI.  */
	cld
	xorl %ebp, %ebp
	movq XOS_THREAD_ENTRY_RUN_OFFSET(%rdi), %rax
	movq XOS_THREAD_ENTRY_ARGUMENT_OFFSET(%rdi), %rdi
	call *%rax
	ud2
	.cfi_endproc
	.size __xos_thread_entry,.-__xos_thread_entry

	.section .note.GNU-stack,"",@progbits
