; Ring3 IPC sender: send "ping\n" to endpoint handle 1, report on success.
bits 64
org 0x40000000

_start:
    mov edi, 1
    lea rsi, [rel message]
    mov edx, 65                 ; oversized message: must be rejected
    mov eax, 4
    int 0x80
    test rax, rax
    jns .skip_length
    lea rdi, [rel bad_length]
    mov esi, bad_length_end - bad_length
    mov eax, 1
    int 0x80
.skip_length:
    mov edi, 1
    mov esi, 0x100000           ; kernel pointer: must be rejected
    mov edx, 4
    mov eax, 4
    int 0x80
    test rax, rax
    jns .skip_pointer
    lea rdi, [rel bad_pointer]
    mov esi, bad_pointer_end - bad_pointer
    mov eax, 1
    int 0x80
.skip_pointer:
    mov edi, 1
    lea rsi, [rel message]
    mov edx, 5
    mov eax, 4                  ; sys_send
    int 0x80
    test rax, rax
    js .delay
    lea rdi, [rel sent]
    mov esi, 3
    mov eax, 1                  ; sys_write
    int 0x80
.delay:
    mov ecx, 0x2fffff
.spin:
    dec ecx
    jnz .spin
    jmp _start

message: db "ping", 10
sent: db "tx", 10
bad_length: db "bad length", 10
bad_length_end:
bad_pointer: db "bad pointer", 10
bad_pointer_end:
