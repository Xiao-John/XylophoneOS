# SPDX-License-Identifier: Apache-2.0
.section .text.entry,"ax",@progbits
.global _start
.extern answer
_start:
    call answer
    cmp $42, %eax
    jne failed
    mov $11, %eax
    mov $1, %edi
    lea message(%rip), %rsi
    mov $11, %edx
    int $0x80
    mov $42, %edi
    jmp finish
failed:
    mov $99, %edi
finish:
    mov $2, %eax
    int $0x80
    ud2
.section .rodata
message:
    .ascii "seed chain\n"
.section .data
    .quad 42
.section .note.GNU-stack,"",@progbits
