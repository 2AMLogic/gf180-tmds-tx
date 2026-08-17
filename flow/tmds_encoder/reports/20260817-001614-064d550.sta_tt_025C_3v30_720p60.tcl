read_lef /root/.volare/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/techlef/gf180mcu_fd_sc_mcu9t5v0__nom.tlef
read_lef /root/.volare/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/lef/gf180mcu_fd_sc_mcu9t5v0.lef
read_liberty /root/.volare/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/lib/gf180mcu_fd_sc_mcu9t5v0__tt_025C_3v30.lib
read_def /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-100/flow/tmds_encoder/pnr/tmds_encoder.def
read_spef /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-100/flow/tmds_encoder/sta/tmds_encoder.spef
read_sdc /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-100/flow/tmds_encoder/reports/20260817-001614-064d550.sta_720p60.sdc

puts "=== SETUP_WORST ==="
report_checks -path_delay max -group_path_count 1 -digits 4
puts "=== HOLD_WORST ==="
report_checks -path_delay min -group_path_count 1 -digits 4
puts "=== REG2REG_SETUP ==="
report_checks -path_delay max -from [all_registers] -to [all_registers] -group_path_count 1 -digits 4
puts "=== REG2REG_HOLD ==="
report_checks -path_delay min -from [all_registers] -to [all_registers] -group_path_count 1 -digits 4
puts "=== WORST_SLACK ==="
report_worst_slack -max -digits 4
report_worst_slack -min -digits 4
puts "=== TNS ==="
report_tns -digits 4
puts "=== SETUP_VIOLATORS ==="
report_checks -path_delay max -slack_max 0 -group_path_count 10000 -format slack_only -digits 4
puts "=== HOLD_VIOLATORS ==="
report_checks -path_delay min -slack_max 0 -group_path_count 10000 -format slack_only -digits 4
puts "=== CLOCK_SKEW ==="
report_clock_skew -setup -digits 4
puts "=== END ==="

exit
