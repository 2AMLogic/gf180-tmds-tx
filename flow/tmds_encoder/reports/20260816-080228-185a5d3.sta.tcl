read_lef /Users/rwalters/.volare/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/techlef/gf180mcu_fd_sc_mcu9t5v0__nom.tlef
read_lef /Users/rwalters/.volare/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/lef/gf180mcu_fd_sc_mcu9t5v0.lef
read_liberty /Users/rwalters/.volare/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/lib/gf180mcu_fd_sc_mcu9t5v0__tt_025C_3v30.lib
read_def /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-85/flow/tmds_encoder/pnr/tmds_encoder.def

define_process_corner -ext_model_index 0 TYP
extract_parasitics -ext_model_file /OpenROAD-flow-scripts/flow/platforms/gf180/openROAD/rcx/gf180mcu_1p5m_1tm_9k_sp_smim_OPTB_typ.rules

write_spef /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-85/flow/tmds_encoder/sta/tmds_encoder.spef
write_sdf /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-85/flow/tmds_encoder/sta/tmds_encoder.sdf

report_checks -unconstrained -group_count 1

exit
