; x86-64 exception/IRQ/syscall entry stubs, frame entry, and GDT reload helper.
bits 64
default rel

extern interrupt_dispatch

section .text

%macro isr_no_error 1
global isr_%1
isr_%1:
    push qword 0
    push qword %1
    jmp interrupt_common
%endmacro

%macro isr_error 1
global isr_%1
isr_%1:
    push qword %1
    jmp interrupt_common
%endmacro

isr_no_error 0
isr_no_error 1
isr_no_error 2
isr_no_error 3
isr_no_error 4
isr_no_error 5
isr_no_error 6
isr_no_error 7
isr_error 8
isr_no_error 9
isr_error 10
isr_error 11
isr_error 12
isr_error 13
isr_error 14
isr_no_error 15
isr_no_error 16
isr_error 17
isr_no_error 18
isr_no_error 19
isr_no_error 20
isr_error 21
isr_no_error 22
isr_no_error 23
isr_no_error 24
isr_no_error 25
isr_no_error 26
isr_no_error 27
isr_no_error 28
isr_error 29
isr_error 30
isr_no_error 31

global irq0_stub
irq0_stub:
    push qword 0
    push qword 32
    jmp interrupt_common

global syscall_stub
syscall_stub:
    push qword 0
    push qword 128
    jmp interrupt_common

global interrupt_common
interrupt_common:
    push rax
    push rbx
    push rcx
    push rdx
    push rsi
    push rdi
    push rbp
    push r8
    push r9
    push r10
    push r11
    push r12
    push r13
    push r14
    push r15

    cld                         ; user DF must never affect kernel C++/copies
    mov rdi, rsp
    and rsp, -16
    call interrupt_dispatch
    mov rsp, rax

    pop r15
    pop r14
    pop r13
    pop r12
    pop r11
    pop r10
    pop r9
    pop r8
    pop rbp
    pop rdi
    pop rsi
    pop rdx
    pop rcx
    pop rbx
    pop rax
    add rsp, 16
    iretq

; Enter a ring3 frame that is already laid out like interrupt_common's stack.
global enter_frame
enter_frame:
    mov rsp, rdi
    pop r15
    pop r14
    pop r13
    pop r12
    pop r11
    pop r10
    pop r9
    pop r8
    pop rbp
    pop rdi
    pop rsi
    pop rdx
    pop rcx
    pop rbx
    pop rax
    add rsp, 16
    mov ax, 0x33
    mov ds, ax
    mov es, ax
    xor eax, eax
    mov fs, ax
    mov gs, ax
    iretq

; rdi points at { u16 limit; u64 base; }.
global gdt_load
gdt_load:
    lgdt [rdi]
    lea rax, [rel .reload]
    push qword 0x08
    push rax
    retfq
.reload:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov fs, ax
    mov gs, ax
    ret

section .rodata align=8
global exception_stub_table
exception_stub_table:
    dq isr_0, isr_1, isr_2, isr_3, isr_4, isr_5, isr_6, isr_7
    dq isr_8, isr_9, isr_10, isr_11, isr_12, isr_13, isr_14, isr_15
    dq isr_16, isr_17, isr_18, isr_19, isr_20, isr_21, isr_22, isr_23
    dq isr_24, isr_25, isr_26, isr_27, isr_28, isr_29, isr_30, isr_31

section .note.GNU-stack noalloc noexec nowrite progbits
