; Ring3 IPC receiver: poll endpoint handle 1, print the message body.
bits 64
org 0x40000000
buffer equ 0x40010000

_start:
    mov edi, 1
    mov rsi, buffer
    mov edx, 32
    mov eax, 5                  ; sys_recv
    int 0x80
    test rax, rax
    jle .delay
    mov rdi, buffer
    mov rsi, rax
    mov eax, 1                  ; sys_write
    int 0x80
.delay:
    mov ecx, 0x2fffff
.spin:
    dec ecx
    jnz .spin
    jmp _start
