; SPDX-License-Identifier: MIT AND Apache-2.0
; Historical MIT base; new XOS CRT options are Apache-2.0.
bits 64
default rel
section .text.entry
global _start
%ifdef XOS_POSIX_MAIN
extern xos_libc_main_entry
%else
extern xos_user_main
%endif
%ifdef XOS_LIBC
extern xos_libc_init
extern xos_libc_finish
%endif
extern _ZN3xos3sdk4exitEi
_start:
    cld
    xor ebp, ebp
    and rsp, -16
%ifdef XOS_POSIX_MAIN
    call xos_libc_main_entry
%else
%ifdef XOS_LIBC
    mov r12, rdi
    call xos_libc_init
    test eax, eax
    jz .libc_ready
    mov edi, 127
    call _ZN3xos3sdk4exitEi
.libc_ready:
    mov rdi, r12
%endif
    call xos_user_main          ; RDI points to versioned startup_info
%ifdef XOS_LIBC
    mov r12d, eax
    call xos_libc_finish
    mov eax, r12d
%endif
%endif
    mov edi, eax
    call _ZN3xos3sdk4exitEi
    ud2
section .note.GNU-stack noalloc noexec nowrite progbits
