; SPDX-License-Identifier: Apache-2.0
; Scratch 0x7000..0x73ff, normalized tail 0x6840..0x686f; payload field untouched.
; Only VBE 2+ direct-color XRGB8888, 800x600 or 640x480 LFB is accepted.
display_probe:
    pushad
    push ds
    push es
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov di, boot_info_address + 64
    mov cx, 48 / 2
    rep stosw
    mov dword [boot_info_address + 8], 2
    mov dword [boot_info_address + 12], 112
    mov dword [boot_info_address + 64], 1
    mov dword [boot_info_address + 68], 48
    mov dword [0x7000], 0x32454256 ; VBE2
    mov ax, 0x4f00
    mov di, 0x7000
    int 0x10
    cmp ax, 0x004f
    jne .done
    cmp dword [0x7000], 0x41534556
    jne .done
    cmp word [0x7004], 0x0200
    jb .done
    mov ax, [0x7010]
    mov [vbe_segment], ax
    mov ax, [0x700e]
    mov [vbe_offset], ax
    mov word [vbe_target], 800
.retry:
    mov ax, [vbe_segment]
    mov fs, ax
    mov si, [vbe_offset]
    mov bp, 512 ; bounded firmware mode-list traversal
.next:
    mov cx, [fs:si]
    add si, 2
    cmp cx, 0xffff
    je .fallback
    push si
    push bp
    push fs
    mov [vbe_mode], cx
    mov ax, 0x4f01
    mov di, 0x7200
    int 0x10
    pop fs
    pop bp
    pop si
    cmp ax, 0x004f
    jne .skip
    mov ax, [0x7200]
    and ax, 0x99 ; supported, color, graphics, linear framebuffer
    cmp ax, 0x99
    jne .skip
    mov ax, [vbe_target]
    cmp [0x7212], ax
    jne .skip
    mov dx, 600
    cmp ax, 800
    je .height
    mov dx, 480
.height:
    cmp [0x7214], dx
    jne .skip
    cmp byte [0x7219], 32
    jne .skip
    cmp byte [0x721b], 6
    jne .skip
    cmp word [0x721f], 0x1008 ; red 8 bits at 16
    jne .skip
    cmp word [0x7221], 0x0808 ; green 8 bits at 8
    jne .skip
    cmp word [0x7223], 0x0008 ; blue 8 bits at 0
    jne .skip
    cmp dword [0x7228], 0
    je .skip
    mov bx, [vbe_mode]
    or bx, 0x4000
    mov ax, 0x4f02
    push si
    push bp
    push fs
    int 0x10
    pop fs
    pop bp
    pop si
    cmp ax, 0x004f
    jne .skip
    xor ax, ax
    mov es, ax
    movzx eax, word [0x7212]
    mov [boot_info_address + 72], eax
    movzx ecx, word [0x7214]
    mov [boot_info_address + 76], ecx
    movzx eax, word [0x7210]
    mov [boot_info_address + 80], eax
    mul ecx
    mov [boot_info_address + 96], eax
    mov eax, [0x7228]
    mov [boot_info_address + 88], eax
    mov dword [boot_info_address + 84], 1
    mov dword [boot_info_address + 104], 1
    jmp .done
.skip:
    dec bp
    jnz .next
.fallback:
    cmp word [vbe_target], 640
    je .done
    mov word [vbe_target], 640
    jmp .retry
.done:
    xor ax, ax
    mov fs, ax
    pop es
    pop ds
    popad
    ret
vbe_segment dw 0
vbe_offset dw 0
vbe_target dw 0
vbe_mode dw 0
