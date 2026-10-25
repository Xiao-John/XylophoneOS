; SPDX-License-Identifier: Apache-2.0
; An old-layout image remains loadable, but opting in must reject its occupied
; new thread arena before allocating anything.
bits 64
default rel
section .text
global _start
_start:
    mov eax, 52
    lea rdi, [header]
    int 0x80
    cmp rax, -18
    jne .fail
    mov eax, 1
    lea rdi, [message]
    mov esi, message_length
    int 0x80
    xor edi, edi
    jmp .done
.fail:
    mov edi, 93
.done:
    mov eax, 2
    int 0x80
    ud2
section .rodata
align 8
header: dd 1,16
        dq 0
message: db '[threading] legacy-arena-explicitly-rejected',10
message_length equ $-message
section .legacy
    db 1
section .note.GNU-stack noalloc noexec nowrite progbits
