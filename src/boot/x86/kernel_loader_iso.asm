; SPDX-License-Identifier: Apache-2.0
; BIOS-only loader. Its normalized output is independent of BIOS and x86.
bits 16
org 0x8000
%include "layout.inc"
%include "kernel_layout.inc"

%define memory_map_address 0x6000
%define boot_info_address 0x6800
%define kernel_blob_address 0x9000

    jmp short loader_start
    dd stage_two_magic

loader_start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7c00
    mov [boot_drive], dl
    cld
    sti
    call serial_init
    mov si, loader_message
    call put_string

    ; QEMU's selected baseline has CPUID; reject missing long mode, NX, or PAE.
    mov eax, 0x80000000
    cpuid
    cmp eax, 0x80000001
    jb cpu_failure
    mov eax, 0x80000001
    cpuid
    and edx, (1 << 29) | (1 << 20)
    cmp edx, (1 << 29) | (1 << 20)
    jne cpu_failure
    mov eax, 1
    cpuid
    test edx, 1 << 6
    jz cpu_failure

    ; Initialize fixed-size normalized header, all reserved fields zero.
    mov di, boot_info_address
    mov cx, 64 / 2
    xor ax, ax
    rep stosw
    mov dword [boot_info_address], 0x49534f58
    mov dword [boot_info_address + 4], 0x314f464e
    mov dword [boot_info_address + 8], 1
    mov dword [boot_info_address + 12], 64
    mov dword [boot_info_address + 20], 24
    mov dword [boot_info_address + 24], kernel_load_address
    mov dword [boot_info_address + 32], kernel_load_address
    mov dword [boot_info_address + 40], kernel_memory_end
    mov dword [boot_info_address + 48], 1 ; BIOS, metadata only

    ; E820 -> 24-byte normalized memory_region, at most 64 nonempty records.
    xor ebx, ebx
    mov di, memory_map_address
    mov word [map_calls], 0
.memory_next:
    inc word [map_calls]
    cmp word [map_calls], 256    ; terminate malformed endless firmware streams
    ja memory_failure
    mov eax, 0xe820
    mov edx, 0x534d4150
    mov ecx, 24
    mov dword [es:di + 20], 1
    push ds
    push di
    int 0x15
    pop di
    pop ds
    jc memory_failure          ; no silent use of an incomplete map
    cmp eax, 0x534d4150
    jne memory_failure
    cmp ecx, 20
    jb memory_failure
    cmp ecx, 24
    jb .attributes_ok
    test dword [di + 20], 1
    jz .memory_skip
.attributes_ok:
    mov eax, [di + 8]
    or eax, [di + 12]
    jz .memory_skip
    mov dword [di + 20], 1
    cmp dword [di + 16], 1
    jb .unknown_type
    cmp dword [di + 16], 5
    jbe .type_ok
.unknown_type:
    mov dword [di + 16], 2     ; unknown firmware memory is reserved
.type_ok:
    inc dword [boot_info_address + 16]
    add di, 24
.memory_skip:
    test ebx, ebx
    jz .memory_done
    cmp dword [boot_info_address + 16], 64
    jae memory_failure
    jmp .memory_next
.memory_done:
    cmp dword [boot_info_address + 16], 0
    je memory_failure
    mov dword [boot_info_address + 52], 1

    ; Prove the entire destination (including BSS/stack) lies in usable RAM.
    mov si, memory_map_address
    mov ecx, [boot_info_address + 16]
.find_kernel_ram:
    cmp dword [si + 16], 1
    jne .next_region
    cmp dword [si + 4], 0
    jne .next_region
    cmp dword [si], kernel_load_address
    ja .next_region
    mov eax, [si]
    mov edx, [si + 4]
    add eax, [si + 8]
    adc edx, [si + 12]
    jc memory_failure
    test edx, edx
    jnz .kernel_ram_ok
    cmp eax, kernel_memory_end
    jae .kernel_ram_ok
.next_region:
    add si, 24
    loop .find_kernel_ram
    jmp memory_failure
.kernel_ram_ok:

    ; The complete boot image is already at 0x7C00; the kernel follows the
    ; loader at a fixed offset. Copy it straight from there in long mode.
    ; Fast A20 gate, then verify with a restored alias probe at 0x500/0x100500.
    in al, 0x92
    and al, 0xfe
    or al, 2
    out 0x92, al
    cli
    mov ax, 0xffff
    mov es, ax
    mov bl, [0x500]
    mov bh, [es:0x510]
    mov byte [0x500], 0
    mov byte [es:0x510], 0xff
    cmp byte [0x500], 0xff
    mov [es:0x510], bh
    mov [0x500], bl
    je a20_failure
    xor ax, ax
    mov es, ax
    call display_probe
    cli
    lgdt [gdt_pointer]
    mov eax, cr0
    or eax, 1
    mov cr0, eax
    jmp 0x08:protected_entry

cpu_failure:
    mov si, cpu_error
    jmp loader_failure
memory_failure:
    mov si, memory_error
    jmp loader_failure
a20_failure:
    xor ax, ax
    mov es, ax
    mov si, a20_error
loader_failure:
    call put_string
    cli
.halt:
    hlt
    jmp .halt

boot_drive db 0
map_calls dw 0
loader_message db "[loader] firmware=bios target=x86_64", 13, 10, 0
cpu_error db "BOOT_ERROR: cpu_requires_long_mode_nx_pae", 13, 10, 0
memory_error db "BOOT_ERROR: memory_map", 13, 10, 0
disk_error db "BOOT_ERROR: kernel_disk_read", 13, 10, 0
a20_error db "BOOT_ERROR: a20", 13, 10, 0

%include "console.inc"
%include "display.inc"

align 8
gdt:
    dq 0
    dq 0x00cf9b000000ffff      ; 0x08: 32-bit code, accessed bit already set
    dq 0x00cf93000000ffff      ; 0x10: data
    dq 0x00af9b000000ffff      ; 0x18: 64-bit code
gdt_end:
gdt_pointer:
    dw gdt_end - gdt - 1
    dd gdt

bits 32
protected_entry:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov fs, ax
    mov gs, ax
    mov esp, 0x7c00
    cld
    mov esi, kernel_blob_address
    mov edi, kernel_load_address
    mov ecx, kernel_file_bytes
    rep movsb

    ; Five 4 KiB tables: PML4, PDPT, PD, PT0, PT1. Identity map first 4 MiB.
    mov edi, 0x1000
    xor eax, eax
    mov ecx, 0x5000 / 4
    rep stosd
    mov dword [0x1000], 0x2003
    mov dword [0x2000], 0x3003
    mov dword [0x3000], 0x4003
    mov dword [0x3008], 0x5003
    mov edi, 0x4000
    xor ebx, ebx
.map_page:
    mov eax, ebx
    or eax, 3                  ; present + writable, supervisor only
    mov edx, 0x80000000        ; NX on data/default mappings
    test ebx, ebx
    jz .null_page
    cmp ebx, 0x8000
    jb .kernel_permissions
    cmp ebx, 0xa000
    jae .kernel_permissions
    and eax, ~2
    xor edx, edx              ; loader transition code is read-only executable
    jmp .store_page
.kernel_permissions:
    cmp ebx, kernel_load_address
    jb .store_page
    cmp ebx, kernel_rodata_start
    jae .rodata
    and eax, ~2
    xor edx, edx              ; kernel text RX
    jmp .store_page
.rodata:
    cmp ebx, kernel_data_start
    jae .store_page
    and eax, ~2               ; rodata R + NX
    jmp .store_page
.null_page:
    xor eax, eax
    xor edx, edx
.store_page:
    mov [edi], eax
    mov [edi + 4], edx
    add edi, 8
    add ebx, 4096
    cmp ebx, 0x400000
    jb .map_page
    mov eax, cr4
    or eax, 1 << 5            ; PAE
    mov cr4, eax
    mov eax, 0x1000
    mov cr3, eax
    mov ecx, 0xc0000080
    rdmsr
    or eax, (1 << 8) | (1 << 11) ; LME + NXE
    wrmsr
    mov eax, cr0
    or eax, (1 << 31) | (1 << 16) ; paging + supervisor write-protect
    mov cr0, eax
    jmp 0x18:long_mode_entry

bits 64
long_mode_entry:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov ss, ax
    xor eax, eax
    mov fs, ax
    mov gs, ax
    mov edi, boot_info_address
    mov esi, memory_map_address
    mov eax, kernel_load_address
    jmp rax                   ; kernel_entry in independently linked ELF
