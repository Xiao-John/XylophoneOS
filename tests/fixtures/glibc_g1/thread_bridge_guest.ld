/* SPDX-License-Identifier: Apache-2.0 */
OUTPUT_FORMAT(elf64-x86-64)
ENTRY(_start)
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); tls PT_TLS FLAGS(4); }
SECTIONS {
  . = 0x40000000;
  .text : { KEEP(*(.text.entry)) *(.text .text.*) *(.rodata .rodata.*) } :text
  . = ALIGN(4096);
  .data : { *(.data .data.*) *(.bss .bss.*) *(COMMON) } :data
  .tdata : { *(.tdata .tdata.*) } :data :tls
  .tbss (NOLOAD) : { *(.tbss .tbss.*) } :data :tls
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
