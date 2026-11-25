/* SPDX-License-Identifier: Apache-2.0 */
OUTPUT_FORMAT(elf64-x86-64)
OUTPUT_ARCH(i386:x86-64)
ENTRY(_start)
PHDRS {
    text PT_LOAD FILEHDR PHDRS FLAGS(5);
    rodata PT_LOAD FLAGS(4);
    data PT_LOAD FLAGS(6);
    tls PT_TLS FLAGS(4);
}
SECTIONS {
    __ehdr_start = 0x40000000;
    . = __ehdr_start + SIZEOF_HEADERS;
    .text : { KEEP(*(.text.entry)) *(.text .text.*) *(.init) *(.fini) *(.plt .iplt) } :text
    . = ALIGN(4096);
    .rodata : { *(.rodata .rodata.*) } :rodata
    .xos.exec : { KEEP(*(.xos.exec)) } :rodata
    .rela.iplt : {
        __rela_iplt_start = .;
        *(.rela.iplt)
        __rela_iplt_end = .;
    } :rodata
    .eh_frame : { KEEP(*(.eh_frame)) } :rodata
    .gcc_except_table : { *(.gcc_except_table .gcc_except_table.*) } :rodata
    . = ALIGN(4096);
    .data : { *(.data .data.*) *(.got .got.*) *(.igot.plt) } :data
    .preinit_array : ALIGN(8) {
        __preinit_array_start = .; KEEP(*(.preinit_array)) __preinit_array_end = .;
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
    .tdata : { *(.tdata .tdata.*) } :data :tls
    .tbss (NOLOAD) : { *(.tbss .tbss.*) *(.tcommon) } :data :tls
    .bss (NOLOAD) : { __bss_start = .; *(.bss .bss.*) *(COMMON) } :data
    _end = .;
    /DISCARD/ : { *(.comment) *(.note*) }
}
