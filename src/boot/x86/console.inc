; 16-bit bring-up console, shared by both stages. DS must address our data.
; Functions preserve general registers; flags are scratch.
serial_init:
    pusha
    mov dx, com_one + 1
    xor al, al
    out dx, al                   ; no UART interrupts
    mov dx, com_one + 3
    mov al, 0x80
    out dx, al                   ; divisor latch
    mov dx, com_one
    mov al, 1
    out dx, al                   ; 115200 baud
    mov dx, com_one + 1
    xor al, al
    out dx, al
    mov dx, com_one + 3
    mov al, 3
    out dx, al                   ; 8 data bits, no parity, 1 stop bit
    mov dx, com_one + 2
    mov al, 0xc7
    out dx, al
    mov dx, com_one + 4
    mov al, 0x0b
    out dx, al
    popa
    ret

serial_put_char:
    pusha
    mov ah, al
    mov cx, 0xffff              ; absent UART must not hang the boot path
    mov dx, com_one + 5
.wait_uart:
    in al, dx
    test al, 0x20
    jnz .send
    loop .wait_uart
    jmp .done
.send:
    mov dx, com_one
    mov al, ah
    out dx, al
.done:
    popa
    ret

put_char:
    call serial_put_char
    pusha
    push ds
    push es
    mov ah, 0x0e
    mov bx, 0x0007              ; page zero, text attribute
    int 0x10
    pop es
    pop ds
    popa
    ret

serial_put_string:              ; serial-only terminal control sequences
    push ax
    push si
.next:
    cld
    lodsb
    test al, al
    jz .done
    call serial_put_char
    jmp .next
.done:
    pop si
    pop ax
    ret

put_string:                     ; DS:SI, NUL terminated
    push ax
    push si
.next:
    cld
    lodsb
    test al, al
    jz .done
    call put_char
    jmp .next
.done:
    pop si
    pop ax
    ret
