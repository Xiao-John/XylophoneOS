; SPDX-License-Identifier: Apache-2.0
bits 64
global _start
global worker_entry
extern probe_main
extern worker_main
section .text.entry
_start:
    and rsp, -16
    call probe_main
    mov rdi, rax
    mov eax, 2
    int 0x80
    ud2
worker_entry:
    and rsp, -16
    call worker_main
    mov rdi, rax
    mov eax, 43
    xor esi, esi
    xor edx, edx
    int 0x80
    ud2
section .note.GNU-stack noalloc noexec nowrite progbits
