; Ring3 heartbeat: print one byte, spin, repeat. The timer must preempt it.
bits 64
org 0x40000000

_start:
    lea rdi, [rel message]
    mov esi, 1
    mov eax, 1                  ; sys_write
    int 0x80
    mov ecx, 0x1fffff
.delay:
    dec ecx
    jnz .delay
    jmp _start

message: db "A"
