foreach k {10 26} {
    read_lib rtl/sram_k${k}.lib
    write_lib adhd_sram_k${k} -format db -output vendor/sram_k${k}.db
}
exit
