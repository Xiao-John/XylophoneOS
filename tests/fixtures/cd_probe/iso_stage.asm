; SPDX-License-Identifier: Apache-2.0
bits 16
org 0x8000
%include "layout.inc"

%define ata_base 0x170
%define ata_ctrl 0x376
%define ata_data ata_base
%define ata_status (ata_base + 7)
%define ata_command (ata_base + 7)
%define ata_drive (ata_base + 6)

%define pvd 0x2000
%define root 0x2800
%define kbuf 0x3000
%define dbuf 0x4000

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

    mov dx, ata_ctrl
    xor al, al
    out dx, al
    mov dx, ata_drive
    mov al, 0xa0
    out dx, al
    mov cx, 4
.select_delay:
    in al, dx
    loop .select_delay
    mov dx, ata_status
    call wait_not_busy
    jc fail
    test al, 0x40
    jz fail

    mov eax, 16
    mov cx, 1
    mov di, pvd
    call read_sectors
    jc fail
    cmp byte [pvd], 1
    jne fail
    cmp byte [pvd + 1], 'C'
    jne fail
    cmp byte [pvd + 2], 'D'
    jne fail
    cmp byte [pvd + 3], '0'
    jne fail
    cmp byte [pvd + 4], '0'
    jne fail
    cmp byte [pvd + 5], '1'
    jne fail

    mov eax, [pvd + 156 + 2]
    mov [root_lba], eax
    mov eax, [pvd + 156 + 10]
    mov [root_size], eax
    add eax, 2047
    shr eax, 11
    mov cx, ax
    mov eax, [root_lba]
    mov di, root
    call read_sectors
    jc fail

    mov si, root
    mov cx, [root_size]
    call find_kernel
    jc fail
    mov si, root
    mov cx, [root_size]
    call find_dash
    jc fail

    cmp byte [kbuf], 'K'
    jne fail
    mov bx, [kernel_size]
    dec bx
    cmp byte [kbuf + bx], '!'
    jne fail
    cmp byte [dbuf], 'D'
    jne fail
    mov bx, [dash_size]
    dec bx
    cmp byte [dbuf + bx], '!'
    jne fail

    mov si, msg_ok
    call put_string
    mov ax, [kernel_size]
    call put_dec
    mov si, msg_dash
    call put_string
    mov ax, [dash_size]
    call put_dec
    mov si, msg_done
    call put_string
    jmp halt
fail:
    mov si, msg_fail
    call put_string
halt:
    cli
    hlt
    jmp halt

; eax = LBA, cx = sector count, di = buffer (ES=0)
read_sectors:
    mov [lba], eax
    mov [remaining], cx
    mov [dest], di
.loop:
    mov eax, [lba]
    bswap eax
    mov [packet + 2], eax
    mov dx, ata_command
    mov al, 0xa0
    out dx, al
    mov dx, ata_status
    call wait_drq
    jc .fail
    mov dx, ata_data
    mov si, packet
    mov cx, 6
.send:
    lodsw
    out dx, ax
    loop .send
    mov dx, ata_status
    call wait_drq
    jc .fail
    mov cx, 1024
    mov di, [dest]
    mov dx, ata_data
    cld
    rep insw
    inc dword [lba]
    add word [dest], 2048
    dec word [remaining]
    jnz .loop
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
    jz .ok
    loop .loop
    stc
    ret
.ok:
    clc
    ret

wait_drq:
    mov cx, 0xffff
.loop:
    in al, dx
    test al, 0x01
    jnz .fail
    test al, 0x08
    jnz .ok
    test al, 0x80
    jnz .loop
    loop .loop
.fail:
    stc
    ret
.ok:
    clc
    ret

; si = directory start, cx = byte count
find_kernel:
    mov di, name_kernel
    mov bx, 0
    call find_entry
    jc .not_found
    mov eax, [si + 2]
    mov edx, [si + 10]
    mov [kernel_size], dx
    mov cx, dx
    add cx, 2047
    shr cx, 11
    mov di, kbuf
    call read_sectors
    ret
.not_found:
    stc
    ret

find_dash:
    mov di, name_dash
    mov bx, 0
    call find_entry
    jc .not_found
    mov eax, [si + 2]
    mov edx, [si + 10]
    mov [dash_size], dx
    mov cx, dx
    add cx, 2047
    shr cx, 11
    mov di, dbuf
    call read_sectors
    ret
.not_found:
    stc
    ret

; si = dir, cx = bytes, di = name to match
; returns si = record, CF clear
find_entry:
    push cx
    mov dx, cx
.next:
    mov al, [si]
    test al, al
    jz .fail
    mov bl, [si + 32]
    cmp bl, [di]
    jne .skip
    push si
    push di
    movzx bx, bl
    lea si, [si + 33]
    inc di
    mov cx, bx
    repe cmpsb
    pop di
    pop si
    je .found
.skip:
    movzx ax, byte [si]
    add si, ax
    sub dx, ax
    jg .next
.fail:
    pop cx
    stc
    ret
.found:
    pop cx
    clc
    ret

put_dec:
    push ax
    push bx
    push cx
    push dx
    mov bx, 10
    xor cx, cx
.div:
    xor dx, dx
    div bx
    push dx
    inc cx
    test ax, ax
    jnz .div
.print:
    pop ax
    add al, '0'
    call put_char
    loop .print
    pop dx
    pop cx
    pop bx
    pop ax
    ret

packet:
    db 0x28, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0
lba: dd 0
remaining: dw 0
dest: dw 0
root_lba: dd 0
root_size: dd 0
kernel_size: dw 0
dash_size: dw 0
name_kernel: db 12, 'KERNEL.BIN;1'
name_dash: db 10, 'DASH.ELF;1'
msg_start: db "A1 start", 13, 10, 0
msg_ok: db "A1 ok KERNEL=", 0
msg_dash: db " DASH=", 0
msg_done: db 13, 10, 0
msg_fail: db "A1 fail", 13, 10, 0
%include "console.inc"
times 0x1000 - ($ - $$) db 0
