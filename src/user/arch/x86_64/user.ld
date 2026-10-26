/* SPDX-License-Identifier: MIT AND Apache-2.0 */
/* Historical MIT base; C++/static TLS layout additions are Apache-2.0. */
OUTPUT_FORMAT(elf64-x86-64)
OUTPUT_ARCH(i386:x86-64)
ENTRY(_start)
PHDRS {
    text PT_LOAD FLAGS(5);
    rodata PT_LOAD FLAGS(4);
    data PT_LOAD FLAGS(6);
    tls PT_TLS FLAGS(4);
}
SECTIONS {
    . = 0x40000000;
    .text : { KEEP(*(.text.entry)) *(.text .text.*) } :text
    . = ALIGN(4096);
    .rodata : { *(.rodata .rodata.*) } :rodata
    .xos.exec : ALIGN(8) { KEEP(*(.xos.exec)) } :rodata
    .eh_frame : ALIGN(8) {
        __eh_frame_start = .;
        KEEP(*(.eh_frame))
        LONG(0)
    } :rodata
    .gcc_except_table : { *(.gcc_except_table .gcc_except_table.*) } :rodata
    . = ALIGN(4096);
    .data : { *(.data .data.*) } :data
    .preinit_array : ALIGN(8) {
        __preinit_array_start = .;
        KEEP(*(.preinit_array))
        __preinit_array_end = .;
    } :data
    .init_array : ALIGN(8) {
        __init_array_start = .;
        KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*))) KEEP(*(.init_array))
        __init_array_end = .;
    } :data
    .fini_array : ALIGN(8) {
        __fini_array_start = .;
        KEEP(*(SORT_BY_INIT_PRIORITY(.fini_array.*))) KEEP(*(.fini_array))
        __fini_array_end = .;
    } :data
    .ctors : ALIGN(8) {
        __ctors_start = .;
        KEEP(*(.ctors)) KEEP(*(SORT(.ctors.*)))
        __ctors_end = .;
    } :data
    .dtors : ALIGN(8) {
        __dtors_start = .;
        KEEP(*(.dtors)) KEEP(*(SORT(.dtors.*)))
        __dtors_end = .;
    } :data
    .tdata : { __xos_tls_template_start = .; *(.tdata .tdata.*) __xos_tls_file_end = .; } :data :tls
    .tbss (NOLOAD) : { *(.tbss .tbss.*) *(.tcommon) __xos_tls_memory_end = .; } :data :tls
    __xos_tls_alignment = MAX(1, MAX(ALIGNOF(.tdata), ALIGNOF(.tbss)));
    .bss (NOLOAD) : { *(.bss .bss.*) *(COMMON) } :data
    __xos_image_end = .;
    /DISCARD/ : { *(.comment) *(.note*) }
}
