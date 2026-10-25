OUTPUT_FORMAT(elf64-x86-64)
OUTPUT_ARCH(i386:x86-64)
ENTRY(kernel_entry)
PHDRS {
    text PT_LOAD FLAGS(5);
    rodata PT_LOAD FLAGS(4);
    data PT_LOAD FLAGS(6);
}
SECTIONS {
    . = 0x100000;
    kernel_start = .;
    .text : { KEEP(*(.text.entry)) *(.text .text.*) } :text
    . = ALIGN(4096);
    rodata_start = .;
    .rodata : { *(.rodata .rodata.*) } :rodata
    . = ALIGN(4096);
    data_start = .;
    .data : { *(.data .data.*) } :data
    kernel_file_end = .;
    . = ALIGN(4096);
    .bss (NOLOAD) : {
        bss_start = .;
        *(.bss .bss.*) *(COMMON)
        . = ALIGN(16);
        kernel_stack_bottom = .;
        . += 16384;
        kernel_stack_top = .;
        bss_end = .;
    } :data
    . = ALIGN(4096);
    kernel_end = .;
    ASSERT(kernel_entry == kernel_start, "entry must start raw kernel payload")
    ASSERT(kernel_end - kernel_start <= 0x300000, "kernel exceeds bootstrap RAM window")
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
