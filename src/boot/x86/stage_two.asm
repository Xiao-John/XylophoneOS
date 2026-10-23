bits 16
org 0x8000
%include "layout.inc"
%include "build_info.inc"

    jmp short stage_two_start
    dd stage_two_magic          ; checked by stage one; not a checksum

stage_two_start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7c00
    cld
    sti
    mov ax, 0x0003              ; BIOS 80x25 text mode, page zero
    int 0x10
    call serial_init
    mov si, welcome_message
    call put_string

show_prompt:
    mov si, prompt
    call put_string
    mov word [input_length], 0
    mov byte [input_overflow], 0

read_input:
    call poll_char
    jnc read_input              ; busy polling is temporary bring-up code
    cmp al, 10
    jne .not_lf
    cmp byte [last_was_cr], 1
    je .skip_lf
    jmp .submit
.skip_lf:
    mov byte [last_was_cr], 0
    jmp read_input
.not_lf:
    mov byte [last_was_cr], 0
    cmp al, 13
    jne .not_cr
    mov byte [last_was_cr], 1
    jmp .submit
.not_cr:
    cmp al, 8
    je .backspace
    cmp al, 127
    je .backspace
    cmp al, 32
    jb read_input
    cmp al, 126
    ja read_input
    cmp byte [input_overflow], 0
    jne read_input
    mov bx, [input_length]
    cmp bx, input_capacity - 1
    jae .overflow
    mov [input_buffer + bx], al
    inc word [input_length]
    call put_char
    jmp read_input
.overflow:
    mov byte [input_overflow], 1 ; reject whole line, never execute truncation
    jmp read_input
.backspace:
    cmp byte [input_overflow], 0 ; overflow stays latched until Enter
    jne read_input
    cmp word [input_length], 0
    je read_input
    dec word [input_length]
    mov si, erase_character
    call put_string
    jmp read_input
.submit:
    mov si, new_line
    call put_string
    cmp byte [input_overflow], 0
    jne line_too_long
    mov bx, [input_length]
    mov byte [input_buffer + bx], 0
    test bx, bx
    jz show_prompt
    mov si, input_buffer
    mov di, help_command
    call strings_equal
    je show_help
    mov di, about_command
    call strings_equal
    je show_about
    mov di, clear_command
    call strings_equal
    je clear_screen
    mov di, halt_command
    call strings_equal
    je halt_system
    mov si, unknown_message
    call put_string
    jmp show_prompt

show_help:
    mov si, help_message
    call put_string
    jmp show_prompt
show_about:
    mov si, about_message
    call put_string
    jmp show_prompt
line_too_long:
    mov si, overflow_message
    call put_string
    jmp show_prompt
clear_screen:
    mov ax, 0x0003
    int 0x10
    mov si, clear_sequence      ; ANSI escape applies only to serial terminal
    call serial_put_string
    mov si, clear_message
    call put_string
    jmp show_prompt
halt_system:
    mov si, halt_message
    call put_string
    cli
.forever:
    hlt
    jmp .forever

poll_char:                      ; CF=1 + AL on input, CF=0 if none
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
    mov dx, com_one + 5
    in al, dx
    test al, 1
    jz .keyboard
    mov dx, com_one
    in al, dx
    jmp .received
.keyboard:
    mov ah, 0x01
    int 0x16
    jz .empty
    xor ah, ah
    int 0x16
    test al, al                 ; ignore extended keys with no ASCII character
    jz .empty
.received:
    stc
    jmp .done
.empty:
    clc
.done:
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    ret

strings_equal:                  ; DS:SI vs DS:DI; ZF=1 if equal, preserves both
    push ax
    push si
    push di
.next:
    mov al, [si]
    cmp al, [di]
    jne .done
    inc si
    inc di
    test al, al
    jnz .next
.done:
    pop di
    pop si
    pop ax
    ret

%include "console.inc"

input_capacity equ 64
input_length dw 0
input_overflow db 0
last_was_cr db 0
input_buffer times input_capacity db 0
prompt db "xos> ", 0
new_line db 13, 10, 0
erase_character db 8, " ", 8, 0
help_command db "help", 0
about_command db "about", 0
clear_command db "clear", 0
halt_command db "halt", 0
welcome_message db "XOS real_mode | build ", xos_build_id, 13, 10
%if xos_easter_eggs
    db "The underscores have won. Type help.", 13, 10, 0
%else
    db "Type help.", 13, 10, 0
%endif
help_message db "help  about  clear  halt", 13, 10, 0
about_message db "XylophoneOS: BIOS real_mode bring-up; x86_64 is next.", 13, 10
    db "No protected memory or user tasks yet.", 13, 10, 0
unknown_message db "ERROR: unknown_command; type help", 13, 10, 0
overflow_message db "ERROR: line_too_long (maximum 63 bytes); discarded", 13, 10, 0
clear_sequence db 27, "[2J", 27, "[H", 0
clear_message db "Screen cleared.", 13, 10, 0
halt_message db "HALTED: CPU resting; close QEMU to exit.", 13, 10, 0
