; SPDX-License-Identifier: Apache-2.0
; Temporary AU0 QEMU route probe. Real-mode test image only; not XOS code.
bits 16
org 0x7c00
start:
    xor ax, ax
    mov ds, ax

    ; PIT channel 2, low/high byte, mode 3, binary.
    mov al, 0xb6
    out 0x43, al
    mov ax, 238                 ; 1193182 / 238 ~= 5013.37 Hz
    out 0x42, al
    mov al, ah
    out 0x42, al

    ; Preserve unrelated speaker-control bits.
    in al, 0x61
    or al, 3                    ; gate channel 2 and enable speaker data
    out 0x61, al

    ; Wait ~1 second using the BIOS tick count driven by PIT channel 0.
    mov eax, [0x046c]
    add eax, 18
.tone_wait:
    cmp eax, [0x046c]
    ja .tone_wait

    ; Disable only the channel-2 gate and speaker-data enable bits.
    in al, 0x61
    and al, 0xfc
    out 0x61, al

    ; Leave ~1 second after the gate clear before halting.
    mov eax, [0x046c]
    add eax, 18
.silence_wait:
    cmp eax, [0x046c]
    ja .silence_wait

.halt:
    hlt
    jmp .halt

times 510-($-$$) db 0
dw 0xaa55
