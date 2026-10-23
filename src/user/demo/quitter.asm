; Ring3 task: report once, exit through syscall, and disappear from the run queue.
bits 64
org 0x40000000

_start:
    lea rdi, [rel message]
    mov esi, message_end - message
    mov eax, 1                  ; sys_write
    int 0x80
    xor edi, edi
    mov eax, 2                  ; sys_exit
    int 0x80
    jmp _start

message: db "bye", 10
message_end:
