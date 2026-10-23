bits 64
default rel
section .text.entry
global _start
extern xos_user_main
extern _ZN3xos3sdk4exitEi
_start:
    cld
    xor ebp, ebp
    and rsp, -16
    call xos_user_main          ; RDI points to versioned startup_info
    mov edi, eax
    call _ZN3xos3sdk4exitEi
    ud2
section .note.GNU-stack noalloc noexec nowrite progbits
