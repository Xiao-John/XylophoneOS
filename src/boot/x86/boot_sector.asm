bits 16
org 0x7c00
%include "layout.inc"

    jmp 0x0000:boot_start        ; normalize either BIOS entry CS:IP convention

boot_start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7c00              ; stack grows below boot sector
    cld
    mov [boot_drive], dl
    sti
    call serial_init
    mov si, loading_message
    call put_string
    mov byte [read_attempts], 3

.read_stage_two:
    xor ax, ax
    mov es, ax
    mov bx, stage_two_address
    mov ah, 0x02
    mov al, stage_two_sectors
    xor ch, ch                  ; cylinder 0, head 0, sectors 2..17
    mov cl, 2
    xor dh, dh
    mov dl, [boot_drive]
    push ds
    int 0x13
    pop ds
    jnc .loaded
    xor ah, ah                  ; reset disk before retrying the whole read
    mov dl, [boot_drive]
    push ds
    int 0x13
    pop ds
    dec byte [read_attempts]
    jnz .read_stage_two
    mov si, disk_error
    jmp boot_failure

.loaded:
    cmp dword [stage_two_address + 2], stage_two_magic
    jne .bad_stage
    mov dl, [boot_drive]
    jmp 0x0000:stage_two_address
.bad_stage:
    mov si, stage_error
boot_failure:
    call put_string
    cli
.halt:
    hlt
    jmp .halt

boot_drive db 0
read_attempts db 0
loading_message db "XOS: loading stage_two", 13, 10, 0
disk_error db "BOOT_ERROR: disk_read", 13, 10, 0
stage_error db "BOOT_ERROR: stage_two_magic", 13, 10, 0

%include "console.inc"

times 510 - ($ - $$) db 0
dw 0xaa55
