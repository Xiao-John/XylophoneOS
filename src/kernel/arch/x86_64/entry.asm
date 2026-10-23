bits 64
default rel
section .text.entry
global kernel_entry
extern kernel_main
extern bss_start
extern bss_end
extern kernel_stack_top

kernel_entry:
    cli
    cld
    mov r12, rdi               ; normalized header
    mov r13, rsi               ; normalized memory regions
    lea rsp, [kernel_stack_top]
    xor ebp, ebp
    lea rdi, [bss_start]
    lea rcx, [bss_end]
    sub rcx, rdi
    xor eax, eax
    rep stosb
    mov rdi, r12
    mov rsi, r13
    call kernel_main           ; stack aligned to 16 before call (SysV AMD64)
    ud2                        ; kernel_main is noreturn

section .note.GNU-stack noalloc noexec nowrite progbits
