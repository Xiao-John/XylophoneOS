; SPDX-License-Identifier: Apache-2.0
bits 16
org 0x8000
%include "layout.inc"

%define ata_base 0x170
%define ata_ctrl 0x376
%define ata_data ata_base
%define ata_error (ata_base + 1)
%define ata_status (ata_base + 7)
%define ata_command (ata_base + 7)
%define ata_drive (ata_base + 6)

start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7c00
    sti
    call serial_init
    mov si, msg_start
    call put_string

    mov byte [unit], 0xa0
    call probe
    jnc .ok
    mov si, msg_retry
    call put_string
    mov byte [unit], 0xb0
    call probe
    jnc .ok
    mov si, msg_fail
    call put_string
    jmp .halt

.ok:
    mov si, msg_ok
    call put_string
    mov si, 0x2001
    mov cx, 5
.print:
    lodsb
    call put_char
    loop .print
    mov si, msg_done
    call put_string
.halt:
    cli
    hlt
    jmp .halt

; CF clear on success, set on failure
probe:
    mov dx, ata_ctrl
    xor al, al
    out dx, al                  ; disable interrupts, polled PIO
    mov dx, ata_status
    call wait_not_busy
    jc .fail
    mov dx, ata_drive
    mov al, [unit]
    out dx, al
    mov cx, 4
.select_delay:
    in al, dx
    loop .select_delay
    mov dx, ata_status
    call wait_not_busy
    jc .fail
    test al, 0x40               ; DRDY
    jz .fail

    mov dx, ata_command
    mov al, 0xa0                ; ATAPI PACKET
    out dx, al
    mov dx, ata_status
    call wait_drq
    jc .fail

    mov dx, ata_data
    mov si, packet
    mov cx, 6
.send_packet:
    lodsw
    out dx, ax
    loop .send_packet

    mov dx, ata_status
    call wait_drq
    jc .fail

    mov di, 0x2000
    mov cx, 1024
    cld
.read_word:
    mov dx, ata_status
    in al, dx
    test al, 0x01
    jnz .fail
    test al, 0x08
    jz .read_word
    mov dx, ata_data
    in ax, dx
    stosw
    loop .read_word
    clc
    ret
.fail:
    stc
    ret

wait_not_busy:
    mov cx, 0xffff
.loop:
    in al, dx
    test al, 0x80
    jz .done
    loop .loop
    stc
    ret
.done:
    clc
    ret

wait_drq:
    mov cx, 0xffff
.loop:
    in al, dx
    test al, 0x01               ; ERR
    jnz .fail
    test al, 0x08               ; DRQ
    jnz .done
    test al, 0x80               ; BSY
    jnz .loop
    loop .loop
.fail:
    stc
    ret
.done:
    clc
    ret

packet:
    db 0x28                     ; READ(10)
    db 0
    db 0, 0, 0, 16              ; LBA 16, big endian
    db 0
    db 0, 1                     ; one 2048-byte block
    db 0, 0, 0

msg_start db "CDTEST start",13,10,0
msg_retry db "CDTEST retry",13,10,0
msg_ok db "CDTEST ok: ",0
msg_done db 13,10,0
msg_fail db "CDTEST fail",13,10,0
unit db 0xa0
%include "console.inc"
times 0x1000 - ($ - $$) db 0
