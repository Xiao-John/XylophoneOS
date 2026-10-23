; Ring3 probe: invalid IPC handle, then read kernel memory and die.
bits 64
org 0x40000000

_start:
    mov edi, 99
    lea rsi, [rel payload]
    mov edx, 4
    mov eax, 4                  ; sys_send, deliberately bad handle
    int 0x80
    test rax, rax
    jns .no_report
    lea rdi, [rel rejected]
    mov esi, rejected_end - rejected
    mov eax, 1                  ; sys_write
    int 0x80
.no_report:
    mov edi, 1                  ; valid numeric handle, but no send right
    lea rsi, [rel payload2]
    mov edx, 4
    mov eax, 4
    int 0x80
    test rax, rax
    jns .no_right
    lea rdi, [rel denied]
    mov esi, denied_end - denied
    mov eax, 1
    int 0x80
.no_right:
    mov rax, [abs 0x100000]     ; supervisor-only kernel text: must fault
    jmp $

payload: db "nope"
payload2: db "nope"
rejected: db "bad handle rejected", 10
rejected_end:
denied: db "no send right", 10
denied_end:
