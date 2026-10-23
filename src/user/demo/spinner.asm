; Ring3 infinite loop with no syscall: only preemption can stop it.
bits 64
org 0x40000000

_start:
    jmp _start
