/* SPDX-License-Identifier: Apache-2.0 */
OUTPUT_FORMAT(elf64-x86-64)
OUTPUT_ARCH(i386:x86-64)
ENTRY(_start)
PHDRS {
    headers PT_PHDR PHDRS FLAGS(4);
    text PT_LOAD FILEHDR PHDRS FLAGS(5);
    note PT_NOTE FLAGS(4);
    stack PT_GNU_STACK FLAGS(6);
}
SECTIONS {
    . = 0x40000000 + SIZEOF_HEADERS;
    .note.xos : ALIGN(4) { KEEP(*(.note.xos)) } :text :note
    .text : ALIGN(16) { *(.text .text.*) } :text
    .rodata : { *(.rodata .rodata.*) } :text
    /DISCARD/ : { *(.comment) *(.eh_frame*) }
}
