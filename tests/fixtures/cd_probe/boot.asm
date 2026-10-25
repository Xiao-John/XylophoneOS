; SPDX-License-Identifier: Apache-2.0
bits 16
org 0x7c00
%include "layout.inc"

    jmp 0x0000:boot_start
boot_start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7c00
    cld
    mov [boot_drive], dl
    sti
    jmp 0x0000:0x8000
boot_drive db 0
times 510 - ($ - $$) db 0
dw 0xaa55
