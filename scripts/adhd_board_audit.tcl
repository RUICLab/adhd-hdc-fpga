# Independent post-route check that the golden query ROM survived synthesis.
set root [file normalize [file join [file dirname [info script]] ..]]
foreach k {10 26} {
    open_checkpoint [file join $root build adhd-board-k$k board_route.dcp]
    set query_rams [get_cells -hier -filter {NAME =~ *golden_q_reg* && REF_NAME =~ RAMB*}]
    if {[llength $query_rams]!=1} {error "Expected one golden-query BRAM for K=$k, got $query_rams"}
    set nonzero 0
    foreach prop [list_property [lindex $query_rams 0]] {
        if {[regexp {^INIT_[0-9A-F][0-9A-F]$} $prop]} {
            set value [get_property $prop [lindex $query_rams 0]]
            if {![regexp -nocase {^256'h0+$} $value]} {incr nonzero}
        }
    }
    if {$nonzero==0} {error "Golden query BRAM initialization is empty for K=$k"}
    set fp [open [file join $root build adhd-board-k$k rom_audit.txt] w]
    puts $fp "BOARD ROM AUDIT PASS K=$k cells=$query_rams nonzero_init_properties=$nonzero"
    puts "BOARD ROM AUDIT PASS K=$k cells=$query_rams nonzero_init_properties=$nonzero"
    close $fp
    close_design
}
exit
