"""gf180-tmds-tx simulation harness.

Reproducible ngspice + gf180mcu PVT (and, for a transient bench, bit-rate)
corner running, ported from `2AMLogic/gf180-bandgap` per CLAUDE.md's
"Verification is the product" mandate and this issue's instruction to reuse
the sim-harness pattern rather than reinventing it, adapted for this repo's
single-rail (DR-0002/DR-0003: driver and synthesized digital domain both on
gf180mcu's 3.3 V core devices) high-speed transient claims. See
sim/README.md.
"""

HARNESS_VERSION = "0.1.0"
