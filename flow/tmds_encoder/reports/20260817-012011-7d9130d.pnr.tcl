read_lef /Users/rwalters/.volare/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/techlef/gf180mcu_fd_sc_mcu9t5v0__nom.tlef
read_lef /Users/rwalters/.volare/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/lef/gf180mcu_fd_sc_mcu9t5v0.lef
read_liberty /Users/rwalters/.volare/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/lib/gf180mcu_fd_sc_mcu9t5v0__tt_025C_3v30.lib
read_verilog /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-110/flow/build/tmds_encoder.pnr_input.v
link_design tmds_encoder

initialize_floorplan -utilization 35 -aspect_ratio 1 -core_space 4 -site GF018hv5v_green_sc9

source /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-110/flow/tmds_encoder/pnr/tracks.tcl

place_pins -hor_layers Metal3 -ver_layers Metal4

tapcell -distance 100 -tapcell_master gf180mcu_fd_sc_mcu9t5v0__filltie -endcap_master gf180mcu_fd_sc_mcu9t5v0__endcap

source /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-110/flow/tmds_encoder/pnr/pdn.tcl
pdngen

global_placement -density 0.45
detailed_placement
optimize_mirroring

# Clock-tree synthesis (issue #100) -- see this module's docstring "Clock-tree
# synthesis" section for the full recipe and rationale. Boundary constraint
# assumptions below are numerically identical to flow/sta_tmds_encoder.py's
# own generated SDC.
create_clock -name clk -period 13.4680 [get_ports clk]
set non_clk_inputs [get_ports {data[*] ctrl[*] de rst}]
set_input_delay 0.0000 -clock clk $non_clk_inputs
set_output_delay 0.0000 -clock clk [all_outputs]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu9t5v0__inv_1 -pin ZN $non_clk_inputs
set_load 0.027252 [all_outputs]

estimate_parasitics -placement
clock_tree_synthesis -buf_list {gf180mcu_fd_sc_mcu9t5v0__clkbuf_1 gf180mcu_fd_sc_mcu9t5v0__clkbuf_2 gf180mcu_fd_sc_mcu9t5v0__clkbuf_3 gf180mcu_fd_sc_mcu9t5v0__clkbuf_4 gf180mcu_fd_sc_mcu9t5v0__clkbuf_8 gf180mcu_fd_sc_mcu9t5v0__clkbuf_12 gf180mcu_fd_sc_mcu9t5v0__clkbuf_16 gf180mcu_fd_sc_mcu9t5v0__clkbuf_20} -sink_clustering_enable
set_propagated_clock [all_clocks]
estimate_parasitics -placement
detailed_placement

# Hold repair (issue #100 step 2): CTS changes per-register clock insertion
# delay, which can turn a pre-CTS-passing hold path into a violation even
# though hold is clock-period-independent (see #83's record, "Known
# limitations" 1). repair_timing legalizes via another detailed_placement.
estimate_parasitics -placement
repair_timing -hold -hold_margin 0.25
detailed_placement

global_route
detailed_route -output_drc /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-110/flow/build/route_drc.rpt -output_maze /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-110/flow/build/maze.log

filler_placement gf180mcu_fd_sc_mcu9t5v0__fill_*

write_def /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-110/flow/tmds_encoder/pnr/tmds_encoder.def
write_verilog /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-110/flow/build/tmds_encoder.pnr.v
write_db /Users/rwalters/GitHub/gf180-tmds-tx/.loom/worktrees/issue-110/flow/build/tmds_encoder.odb

exit
