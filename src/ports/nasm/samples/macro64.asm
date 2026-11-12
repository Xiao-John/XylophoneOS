; Preprocessor + ELF64 self-test shipped with the NASM package.
BITS 64
default rel
section .text
%define SYS_exit 60
%macro set_exit 1
    mov eax, SYS_exit
    mov edi, %1
%endmacro
global _start
_start:
    set_exit 0
    syscall
%rep 2
    nop
%endrep
