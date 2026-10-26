; SPDX-License-Identifier: Apache-2.0
; BIOS-only loader. Its normalized output is independent of BIOS and x86.
bits 16
org 0x8000
%include "layout.inc"
%include "kernel_layout.inc"

%define memory_map_address 0x6000
%define boot_info_address 0x6800
%define payload_descriptor 0x6900
%define page_table_base 0x10000
%define low_map_bytes 0x1200000

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
    call load_kernel32
    jnc load_done_32
    mov esi, [cd_error_message]
.error_next:
    lodsb
    test al, al
    jz .error_halt
    mov dx, 0x3f8
    out dx, al
    jmp .error_next
.error_halt:
    cli
    hlt
    jmp .error_halt
; --- 32-bit ATAPI + ISO9660 kernel load --------------------------------
%define cd_base 0x170
%define cd_ctrl 0x376
%define cd_data cd_base
%define cd_status (cd_base + 7)
%define cd_command (cd_base + 7)
%define cd_drive (cd_base + 6)

load_kernel32:
    mov dx, cd_ctrl
    mov al, 2                 ; mask device IRQ; bounded polling only
    out dx, al
    mov dx, cd_drive
    mov al, 0xa0
    out dx, al
    mov ecx, 4
.select_delay:
    in al, dx
    loop .select_delay
    mov dx, cd_status
    call cd_wait_not_busy
    jc .fail
    test al, 0x40
    jz .fail

    mov eax, 16
    mov edi, 0x2000
    call cd_read_one
    jc .fail
    mov dword [cd_error_message], directory_error
    cmp byte [0x2000], 1
    jne .fail
    cmp dword [0x2001], 0x30304443
    jne .fail
    cmp byte [0x2005], '1'
    jne .fail
    cmp byte [0x2006], 1
    jne .fail
    cmp word [0x2080], 2048
    jne .fail
    mov eax, [0x2050]
    test eax, eax
    jz .fail
    mov [cd_volume_sectors], eax
    bswap eax
    cmp eax, [0x2054]
    jne .fail
    mov eax, [0x209e]
    mov [cd_root_lba], eax
    mov eax, [0x20a6]
    test eax, eax
    jz .fail
    cmp eax, 2048
    ja .fail
    mov [cd_root_size], eax
    mov dword [cd_file_sectors], 1
    mov eax, [cd_root_lba]
    mov [cd_file_lba], eax
    call check_extent
    jc .fail
    mov edi, 0x2800
    call cd_read_one
    jc .fail

    mov ebp, cd_kernel_name
    mov ecx, 12
    call find_record
    jc .fail
    mov eax, [ebx + 10]
    mov edx, eax
    bswap edx
    cmp edx, [ebx + 14]
    jne .fail
    mov dword [cd_error_message], kernel_size_error
    cmp eax, kernel_file_bytes
    jne .fail
    cmp eax, iso_kernel_max_file_bytes
    ja .fail
    mov [cd_file_size], eax
    add eax, 2047
    jc .fail
    shr eax, 11
    mov [cd_file_sectors], eax
    mov eax, [ebx + 2]
    mov [cd_file_lba], eax
    call check_extent
    jc .fail
    mov edi, kernel_load_address
    call read_file
    jc .fail

    mov ebp, cd_dash_name
    mov ecx, 10
    call find_record
    jnc .payload_found
    cmp dword [cd_missing], 1
    je .no_payload
    jmp .fail
.payload_found:
    mov eax, [ebx + 10]
    mov edx, eax
    bswap edx
    cmp edx, [ebx + 14]
    jne .fail
    mov dword [cd_error_message], payload_size_error
    test eax, eax
    jz .fail
    cmp eax, iso_payload_max_bytes
    ja .fail
    mov [cd_payload_size], eax
    add eax, 2047
    jc .fail
    and eax, ~2047
    mov edx, eax
    add edx, iso_payload_address
    jc .fail
    mov eax, iso_payload_address
    mov dword [cd_error_message], payload_memory_error
    call check_ram
    jc .fail
    mov eax, [ebx + 2]
    mov [cd_file_lba], eax
    mov eax, [cd_payload_size]
    add eax, 2047
    shr eax, 11
    mov [cd_file_sectors], eax
    call check_extent
    jc .fail
    mov edi, iso_payload_address
    call read_file
    jc .fail
    mov dword [payload_descriptor], 0x534f5858
    mov dword [payload_descriptor + 4], 0x31444c50
    mov dword [payload_descriptor + 8], iso_payload_address
    mov dword [payload_descriptor + 12], 0
    mov eax, [cd_payload_size]
    mov [payload_descriptor + 16], eax
    mov dword [payload_descriptor + 20], 0
    mov dword [boot_info_address + 56], payload_descriptor
    mov dword [boot_info_address + 60], 0
.no_payload:
    clc
    ret
.fail:
    stc
    ret

; Validate each root record before comparing its name. CF + missing=1 is optional absence.
find_record:
    mov [cd_name_length], ecx
    mov esi, 0x2800
    mov dword [cd_missing], 0
.next:
    mov edx, 0x2800
    add edx, [cd_root_size]
    cmp esi, edx
    jae .missing
    movzx eax, byte [esi]
    test eax, eax
    jz .missing
    cmp eax, 34
    jb .bad
    mov ebx, esi
    add eax, esi
    cmp eax, edx
    ja .bad
    movzx edx, byte [esi + 32]
    add edx, 33
    add edx, esi
    cmp edx, eax
    ja .bad
    test byte [esi + 25], 0x82 ; no directories or multi-extent files
    jnz .skip
    mov ecx, [cd_name_length]
    movzx edx, byte [esi + 32]
    cmp edx, ecx
    jne .skip
    lea esi, [esi + 33]
    mov edi, ebp
    repe cmpsb
    je .found
.skip:
    mov esi, eax
    jmp .next
.found:
    clc
    ret
.missing:
    mov dword [cd_missing], 1
.bad:
    mov dword [cd_error_message], directory_error
    stc
    ret

check_extent:
    mov eax, [cd_file_lba]
    cmp eax, [cd_volume_sectors]
    jae .bad
    mov edx, [cd_volume_sectors]
    sub edx, eax
    cmp [cd_file_sectors], edx
    ja .bad
    clc
    ret
.bad:
    mov dword [cd_error_message], extent_error
    stc
    ret

; EAX=first, EDX=rounded end. Keep EBX (the directory entry) intact.
check_ram:
    push ebx
    mov ebp, eax
    mov edi, edx
    mov esi, memory_map_address
    mov ecx, [boot_info_address + 16]
    xor ebx, ebx
.next:
    cmp dword [esi + 4], 0
    jne .skip
    cmp [esi], edi
    jae .skip
    mov eax, [esi]
    mov edx, [esi + 4]
    add eax, [esi + 8]
    adc edx, [esi + 12]
    jc .bad
    test edx, edx
    jnz .overlap
    cmp eax, ebp
    jbe .skip
.overlap:
    cmp dword [esi + 16], 1
    jne .bad
    cmp [esi], ebp
    ja .skip
    test edx, edx
    jnz .covered
    cmp eax, edi
    jb .skip
.covered:
    mov ebx, 1
.skip:
    add esi, 24
    loop .next
    test ebx, ebx
    jz .bad
    pop ebx
    clc
    ret
.bad:
    pop ebx
    stc
    ret

read_file:
    mov dword [cd_error_message], read_error
.next:
    cmp dword [cd_file_sectors], 0
    je .done
    mov eax, [cd_file_lba]
    call cd_read_one
    jc .fail
    inc dword [cd_file_lba]
    dec dword [cd_file_sectors]
    jmp .next
.done:
    clc
    ret
.fail:
    stc
    ret

; EAX=LBA, EDI=destination; EDI advances by 2048
cd_read_one:
    mov [cd_lba], eax
    bswap eax
    mov [cd_packet + 2], eax
    mov dx, cd_status
    call cd_wait_not_busy
    jc .fail
    mov dx, cd_base + 1
    xor al, al
    out dx, al
    mov dx, cd_base + 4
    xor al, al
    out dx, al
    inc dx
    mov al, 8
    out dx, al
    mov dx, cd_command
    mov al, 0xa0
    out dx, al
    mov dx, cd_status
    call cd_wait_drq
    jc .fail
    mov dx, cd_data
    mov esi, cd_packet
    mov ecx, 6
.send:
    lodsw
    out dx, ax
    loop .send
    mov dx, cd_status
    call cd_wait_drq
    jc .fail
    mov ecx, 1024
    mov dx, cd_data
    cld
    rep insw
    clc
    ret
.fail:
    stc
    ret

cd_wait_not_busy:
    mov ecx, 0xffff
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

cd_wait_drq:
    mov ecx, 0xffff
.loop:
    in al, dx
    test al, 0x80
    jnz .again
    test al, 0x21
    jnz .fail
    test al, 0x08
    jnz .ok
.again:
    loop .loop
.fail:
    stc
    ret
.ok:
    clc
    ret

cd_packet:
    db 0x28, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0
cd_error_message: dd read_error
cd_volume_sectors: dd 0
cd_name_length: dd 0
cd_missing: dd 0
cd_payload_size: dd 0
read_error: db "BOOT_ERROR: iso_read", 13, 10, 0
directory_error: db "BOOT_ERROR: iso_directory", 13, 10, 0
kernel_size_error: db "BOOT_ERROR: iso_kernel_size", 13, 10, 0
payload_size_error: db "BOOT_ERROR: iso_payload_size", 13, 10, 0
payload_memory_error: db "BOOT_ERROR: iso_payload_memory", 13, 10, 0
extent_error: db "BOOT_ERROR: iso_extent", 13, 10, 0
cd_lba: dd 0
cd_root_lba: dd 0
cd_root_size: dd 0
cd_file_lba: dd 0
cd_file_size: dd 0
cd_file_sectors: dd 0
cd_dash_lba: dd 0
cd_dash_size: dd 0
cd_kernel_name:
    db 'KERNEL.BIN;1'
cd_dash_name:
    db 'DASH.ELF;1'
load_done_32:

    ; Nine leaf tables at 0x10000 cover 18 MiB, preserving kernel W^X beyond 4 MiB.
    mov edi, 0x1000
    xor eax, eax
    mov ecx, 0x5000 / 4
    rep stosd
    mov dword [0x1000], 0x2003
    mov dword [0x2000], 0x3003
    mov edi, page_table_base
    xor eax, eax
    mov ecx, (low_map_bytes / 0x200000) * 4096 / 4
    rep stosd
    mov edi, 0x3000
    mov eax, page_table_base | 3
    mov ecx, low_map_bytes / 0x200000
.link_leaf:
    stosd
    add edi, 4
    add eax, 4096
    loop .link_leaf
    mov edi, page_table_base
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
    cmp ebx, low_map_bytes
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
