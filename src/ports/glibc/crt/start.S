/* SPDX-License-Identifier: Apache-2.0 */
.section .text.entry,"ax",@progbits
.global _start
.type _start,@function
_start:
    cld
    xor %ebp,%ebp
    and $-16,%rsp
    mov %rsp,%rsi
    call __xos_glibc_start
    ud2
.size _start,.-_start
.section .note.GNU-stack,"",@progbits
