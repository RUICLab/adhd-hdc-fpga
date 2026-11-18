OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0, LENGTH = 512K }
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text .text.*) } > RAM
 .rodata : { *(.rodata .rodata.*) } > RAM
 .data : { *(.data .data.* .sdata .sdata.*) } > RAM
 .bss (NOLOAD) : { . = ALIGN(4); _bss_start = .; *(.bss .bss.* .sbss .sbss.* COMMON) . = ALIGN(4); _bss_end = .; } > RAM
 _stack_top = ORIGIN(RAM) + LENGTH(RAM) - 16;
 ASSERT(_bss_end < _stack_top - 16384, "Reserve 16KiB stack")
}
