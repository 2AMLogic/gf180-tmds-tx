read_lef /Users/rwalters/.volare/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/techlef/gf180mcu_fd_sc_mcu9t5v0__nom.tlef
read_lef /Users/rwalters/.volare/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/lef/gf180mcu_fd_sc_mcu9t5v0.lef
read_liberty /Users/rwalters/.volare/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/lib/gf180mcu_fd_sc_mcu9t5v0__tt_025C_3v30.lib
read_verilog /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-84/flow/build/tmds_encoder.pnr_input.v
link_design tmds_encoder

initialize_floorplan -utilization 35 -aspect_ratio 1 -core_space 4 -site GF018hv5v_green_sc9

source /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-84/flow/tmds_encoder/pnr/tracks.tcl

place_pins -hor_layers Metal3 -ver_layers Metal4

tapcell -distance 100 -tapcell_master gf180mcu_fd_sc_mcu9t5v0__filltie -endcap_master gf180mcu_fd_sc_mcu9t5v0__endcap

source /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-84/flow/tmds_encoder/pnr/pdn.tcl
pdngen

global_placement -density 0.45
detailed_placement
optimize_mirroring

global_route
detailed_route -output_drc /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-84/flow/build/route_drc.rpt -output_maze /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-84/flow/build/maze.log

filler_placement gf180mcu_fd_sc_mcu9t5v0__fill_*

write_def /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-84/flow/tmds_encoder/pnr/tmds_encoder.def
write_verilog /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-84/flow/build/tmds_encoder.pnr.v
write_db /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-84/flow/build/tmds_encoder.odb

exit
