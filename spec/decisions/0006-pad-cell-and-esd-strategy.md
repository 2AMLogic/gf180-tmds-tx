# 0006 — Adapt `gf180mcu_fd_io__asig_5p0`; 2 kV HBM / 500 V CDM

**Status:** Accepted 2026-08-05.

> **Division of labour with #2.** #2 owns the *factual* PDK pad-ring and ESD
> survey — what pitches, ESD devices, and reference structures gf180mcu
> actually offers, and what `klt drc` / `klt lvs` do at a pad boundary. This
> record owns the *decision*: which structure to start from and what ESD
> level to target. Where the two disagree, #2's extracted and DRC-verified
> numbers win on facts, and this record is superseded rather than edited.
> The survey below is what could be established directly from the installed
> PDK at ratification time; it is a starting point for #2, not a substitute
> for it.

## Context

The block needs a pad that carries 742.5 Mbps, sits DC-coupled at up to
3.465 V, sinks 10 mA, and survives ESD — and gf180mcu's I/O library was built
for none of that. The complete library
(`libs.ref/gf180mcu_fd_io/lef/`, 15 macros) is:

| Cell | Size (µm) | Class |
|---|---|---|
| `gf180mcu_fd_io__bi_t`, `bi_24t`, `gf180mcu_ef_io__bi_t` | 75 × 350 | PAD INOUT (5 V GPIO) |
| `gf180mcu_fd_io__in_c`, `in_s` | 75 × 350 | PAD INPUT |
| `gf180mcu_fd_io__asig_5p0` | 75 × 350 | PAD INOUT (analog pass-through) |
| `dvdd`, `dvss` | 75 × 350 | PAD POWER |
| `brk2`, `brk5` | 2 / 5 × 350 | PAD (rail break) |
| `fill1`, `fill5`, `fill10`, `fillnc` | 1 / 5 / 10 / 0.1 × 350 | PAD SPACER |
| `cor` | 355 × 355 | ENDCAP BOTTOMLEFT |

Every signal cell is 75.000 × 350.000 µm on `SITE GF_IO_Site`. There is no
high-speed cell, no differential cell, and no current-mode cell — which is
what makes this block's pad ring the canary's central risk.

`asig_5p0` is the only bare analog pass-through: pad to ESD to core, no
buffer. Its structure, from
`libs.ref/gf180mcu_fd_io/spice/gf180mcu_fd_io.spice`:

```
.SUBCKT gf180mcu_fd_io__asig_5p0 ASIG5V DVDD DVSS VDD VSS
D0 DVSS DVDD diode_nd2ps_06v0 m=4.0 area=40e-12  pj=82e-6     ; rail clamp
X1 DVDD DVSS cap_nmos_06v0 m=36.0 c_length=15e-6 c_width=15e-6 ; 8100 µm² rail decap
D2 DVSS ASIG5V diode_nd2ps_06v0 m=4.0 area=150e-12 pj=106e-6  ; pad → VSS
D3 ASIG5V DVDD diode_pd2nw_06v0 m=4.0 area=150e-12 pj=106e-6  ; pad → VDD
.ENDS
```

That is the textbook dual-diode-plus-rail-clamp scheme: 600 µm² of diode per
polarity steering the strike to the rails, and a large rail clamp taking it
across. Its ESD performance is the PDK vendor's, qualified on silicon we did
not fab and cannot re-qualify — and neither `klt drc` nor `klt lvs` can check
an ESD level, so redrawing it would mean *replacing qualified geometry with
unverifiable geometry*.

Against that: ESD area is pad capacitance, and pad capacitance is the
bandwidth budget. Computed from the model cards in
`libs.tech/ngspice/sm141064.ngspice`:

| Diode | cjo | cjp/cjsw | pb | mj | Zero-bias | At TMDS bias |
|---|---|---|---|---|---|---|
| `D2` `diode_nd2ps_06v0` ×4 | 0.95 fF/µm² | 0.133 fF/µm | 0.606 | 0.296 | 626 fF | 392 fF (≈3 V reverse) |
| `D3` `diode_pd2nw_06v0` ×4 | 0.912 fF/µm² | 0.1465 fF/µm | 0.768 | 0.327 | 609 fF | 560 fF (≈0.25 V reverse) |
| | | | | | **1235 fF** | **≈952 fF** |

`D3` barely depletes because a DC-coupled TMDS pad *idles at the positive
rail* — V_OH = AV_CC, so the pad-to-AVDD diode sees almost no reverse bias.
That is specific to this signaling scheme and is why the pad-to-rail diode,
not the pad-to-ground diode, dominates here.

And the capacitance has a **floor**, not just a ceiling. The pad node is one
pole against the sink's 50 Ω; the 10–90% edge is 2.2 · 50 Ω · C_PAD:

| C_PAD | 10–90% edge | vs. the 75–539 ps window (DVI min rise / 0.4 UI) |
|---|---|---|
| 0.6 pF | 66 ps | **Below the 75 ps minimum** |
| 0.8 pF | 88 ps | Just inside |
| 2.0 pF | 220 ps | Comfortable |
| 3.0 pF | 330 ps | OK at 720p60; 0.49 UI at 1080p60 — fails |

So stripping ESD capacitance to "go faster" would push the edges past the
minimum rise time the standard imposes for EMI reasons. The ESD array is not
purely a cost.

## Decision

1. **Adapt `gf180mcu_fd_io__asig_5p0`. Do not draw a pad from scratch.**
   Retain its 75.000 × 350.000 µm footprint, its `SITE GF_IO_Site`
   placement, and its dual-diode + rail-clamp ESD topology and geometry.
2. **What changes:** the internal routing from the pad to the core, so the
   pad connects to the driver cascode drain with controlled, minimized
   capacitance and a current path able to carry 10 mA continuously; and the
   ESD clamp reference, from the source cell's 5 V `DVDD`/`DVSS` to this
   block's **`AVDD_TMDS` / `AVSS_TMDS`** (3.3 V).
3. **ESD target: 2 kV HBM (JEDEC JS-001 Class 2) and 500 V CDM (JS-002 Class
   C3), all pads.** This is the level the source structure is sized for; it
   is adopted rather than exceeded because raising it means more diode area,
   and diode area is the capacitance budget below.
4. **C_PAD: 0.8 pF ≤ C_PAD ≤ 2.0 pF. Both bounds binding.** Includes ESD
   diodes, pad metal, cascode drain, and pad-to-core routing.
5. **Why the ESD rails are the analog rails, not the 5 V I/O rails:** an ESD
   strike on a TMDS pad must return to the same rail pair the driver's own
   current uses, so that the clamp, the driver, and the strike share one
   low-impedance loop. Referencing the pad clamps to a rail the driver is not
   on would put a package inductance in the middle of the discharge path.
6. **Ratified contingency, if #2's extraction shows C_PAD > 2.0 pF.** In
   priority order: (a) reduce the `D3` (pad-to-AVDD) multiplicity first, since
   it contributes 560 of the 952 fF for the reason above; (b) if that is not
   enough, reduce `D2`; (c) only then consider re-referencing `D3` to a 5 V
   rail, which drops it to ≈430 fF at 1.7 V reverse bias but adds a supply
   domain and a second discharge loop. Any of these **lowers the achieved
   HBM level below 2 kV** and therefore **requires a new decision record**
   stating the extracted capacitance, the option taken, and the resulting
   ESD level. It may not be done silently to make a bandwidth number pass.

## Alternatives considered

- **Draw the pad and its ESD structure entirely from scratch.** Rejected.
  The appeal is a capacitance-optimal structure; the cost is that ESD
  robustness is exactly the property no tool in this flow can check — not
  `klt drc`, not `klt lvs`, not ngspice. Redrawing swaps vendor-qualified
  geometry for geometry whose only evidence would be our own assertion. The
  canary's value here is in the *pad-to-driver seam*, which is novel either
  way; the ESD diodes are not where the interesting failure lives.
- **Use `gf180mcu_fd_io__bi_t` (the 5 V GPIO) directly.** Rejected: it
  contains a full 5 V push-pull output buffer and level shifters between the
  pad and the core. A TMDS driver must present a high-impedance current sink,
  which is electrically the opposite; the buffer would have to be deleted,
  leaving `asig_5p0` — which is what `asig_5p0` already is.
- **Target 4 kV HBM.** Rejected: roughly doubles diode area and therefore
  adds ≈1 pF, blowing the 2.0 pF budget on its own, for a level no
  requirement asks for. 2 kV / Class 2 is the standard commercial floor.
- **Target 1 kV HBM to buy capacitance headroom up front.** Rejected as
  premature. The computed ≈952 fF already fits inside 2.0 pF with ≈1.05 pF to
  spare for pad metal and the cascode drain. Relaxing ESD before knowing the
  extracted number would be trading away a real property for margin that may
  not be needed — which is why it appears as a *contingency* with an
  objective trigger instead.
- **Share one ESD cell between the P and N pads of a pair.** Rejected:
  couples the two sides of a differential pair through the clamp, and the
  common-mode/differential behavior of that coupling during normal operation
  would need analysis nothing in this flow can perform.
- **Place the driver output stage inside the pad cell** (a true custom
  high-speed I/O). Rejected for now — a larger and more interesting piece of
  work than #2 is scoped for, and it would make the pad cell's DRC/LVS result
  inseparable from the driver's. Revisit once a plain adapted pad has been
  through `klt drc` and `klt lvs` cleanly; that ordering is the point of #2.

## Consequences

- #2 inherits a bounded task: adapt one known cell, keep the footprint,
  extract C_PAD, and put it through `klt drc` and `klt lvs`. It does not have
  to invent an ESD structure.
- The pad ring is on a 75 µm pitch with a 350 µm depth and a 355 µm corner
  cell. Eight TMDS pads plus their flanking `AVSS_TMDS` returns, the supply
  pads, `IREF_EXT`, `pix_clk_o`, and the digital interface set the die
  perimeter. That floorplan consequence is #2's to work out.
- **This block claims no ESD verification.** The 2 kV / 500 V figure rests on
  reusing the PDK's qualified structure unchanged; no ESD simulation or test
  is performed, and none is available in this flow. Recorded as `tmds-tx.md`
  §10, O-5. Any statement stronger than "reuses the PDK's `asig_5p0` ESD
  structure at its rated level" is unsupported.
- The 0.8 pF floor means a later optimization that *removes* pad capacitance
  can break compliance. Anyone reducing C_PAD must check the rise-time
  window, not just the bandwidth.
- The capacitance numbers above are hand calculations from model cards
  (`tmds-tx.md` §10, O-2). #2's extraction supersedes them on fact; the
  ratified 0.8–2.0 pF window and the contingency in §6 stand until a new
  record changes them.
