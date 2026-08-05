# 0004 — Cascoded current-steering driver, device flavors, supply domains

**Status:** Accepted 2026-08-05.

## Context

TMDS is DC-coupled and current-mode. The sink terminates each line with
50 Ω to its own AV_CC (3.3 V ±5%, so 3.135–3.465 V). The transmitter is a
high-impedance current sink: a tail current steered between the two lines of
a pair. The line carrying current sits V_SWING below AV_CC; the other sits at
AV_CC. For a 500 mV single-ended swing into 50 Ω, the tail current is
**10 mA**.

Two consequences follow immediately and shape everything else:

1. **The pad idles at the sink's AV_CC, up to 3.465 V.** The output devices
   see that voltage whenever their leg is off.
2. **The DC current is supplied by the sink, not by this block.** It returns
   through this block's AVSS_TMDS, dissipating ≈10 mA × 2.8 V ≈ 28 mW per
   lane on this die regardless of what our own AVDD delivers.

The device options in gf180mcu (`libs.tech/ngspice/sm141064.ngspice`):

| Flavor | L_min | Rating | Notes |
|---|---|---|---|
| `nfet_03v3` / `pfet_03v3` | 0.28 µm | 3.3 V | Fast. Five process corners available: `typical`, `ff`, `ss`, `fs`, `sf`. |
| `nfet_06v0` / `pfet_06v0` | 0.60 / 0.50 µm | 6.0 V | Slow. **Typical model only** — see below. |
| `nfet_06v0_nvt` | 1.8 µm | 6.0 V | Native (near-zero V_TH). Typical model only. |

A 3.3 V device with 3.465 V across it is outside its rating. A 6 V device is
not — but there is a second, decisive fact. The five corner sections in
`sm141064.ngspice` (lines 105, 140, 175, 210, 245) skew **only** the 3.3 V
devices; every one of them pulls in `nfet_06v0_t`, `pfet_06v0_t`, and
`nfet_06v0_nvt_t`. The open PDK ships **no process skew for 6 V devices in
ngspice at all**.

The repo's own rule is "PVT corners on every recorded analog result." A
driver whose current- and speed-determining devices are 6 V devices cannot
produce such a result, with these models, ever. That is not a preference; it
is a hard constraint on what this block can claim.

Third constraint: `tmds-tx.md` §7 caps the pad-node capacitance at 2.0 pF,
and the ESD diodes alone account for ≈0.95 pF. Whatever capacitance the
output stage presents to the pad comes out of the ≈1.05 pF that remains.

Fourth: V_SWING = I_TAIL × R_T must land inside the DVI 400–600 mV window
while R_T itself is allowed ±10%. That leaves ±10% for I_TAIL — tighter than
any on-chip resistor can hold. The `res` section of `sm141064.ngspice`
carries poly-resistor spreads far wider than that.

## Decision

**Topology: differential current-steering pair with a common-gate cascode.**

```
        TX_P  o------+----------------+------o  TX_N
                     |                |          (each to sink: 50 Ω to AV_CC)
                  [ M_CASC_P ]     [ M_CASC_N ]   nfet_06v0, common gate, V_BIAS_CASC
                     |                |
                  [ M_SW_P ]       [ M_SW_N ]     nfet_03v3, CML-driven switch pair
                     +-------+--------+
                             |
                        [ M_TAIL ]                nfet_03v3, long-L current source
                             |
                            AVSS_TMDS
```

1. **Switch pair: `nfet_03v3`.** These are the only devices in the signal
   path that toggle at 742.5 Mbps, and the only ones whose process corners
   can be simulated.
2. **Cascode: `nfet_06v0`, common gate, fixed bias.** It absorbs the pad
   voltage (up to 3.465 V) so the switch-pair drains stay well inside the
   3.3 V rating, and it isolates the switch drain capacitance from the pad.
   Because it is common-gate and never switches, its process spread affects
   the output current only through its V_TH-dependent bias headroom — a
   second-order effect, which is what makes the missing 6 V corners
   survivable rather than disqualifying.
3. **Tail: `nfet_03v3`, long channel** for output resistance. Its drain sits
   low, so it is inside its rating.
4. **I_TAIL = 10.0 mA ±10% over PVT**, mirrored from a reference set by an
   **external 1.00 kΩ ±1% resistor** on a dedicated `IREF_EXT` pad, plus a
   4-bit monotonic trim (≥ ±20% range, ≤ 3% steps) for characterization.
5. **Supply domains:**
   | Domain | Nominal | Corners | Scope |
   |---|---|---|---|
   | `DVDD` / `DVSS` | 3.30 V | 3.00 / 3.30 / 3.60 V | Synthesized encoder |
   | `AVDD_TMDS` / `AVSS_TMDS` | 3.30 V | 3.135 / 3.300 / 3.465 V | Driver, CML, bias, custom serializer |

   Separately bonded. `AVDD_TMDS` uses the ±5% window because the analog
   side must interoperate with a DVI AV_CC held to ±5%; `DVDD` uses the
   ±9% window because those are the supplies at which the standard-cell
   liberty is characterized, so STA runs on data that exists.
6. **The block must be verified with the pad held at 3.465 V with the driver
   off** — this is the condition the cascode exists for, and the one that
   would be silently skipped if the testbench only ever drove data.
7. **Sensitivity to the cascode's unmodelled process spread must be recorded**
   (a manual V_TH / µ sweep on the cascode device, since no corner exists)
   before any driver result is entered as evidence.

## Alternatives considered

- **All-6 V output stage (switches, cascode, tail all `nfet_06v0`).** The
  simplest and most overvoltage-robust option; no cascode bias needed at all,
  since a 6 V device tolerates 3.465 V directly. **Rejected on verifiability
  first, speed second.** With no 6 V process corners in ngspice, the tail
  current's process spread — the parameter that sets V_SWING, the block's
  headline number — would be unsimulable. The block could not honestly claim
  a PVT-cornered swing. Secondarily, L = 0.6 µm switches at 742.5 Mbps need
  large widths, and their gate capacitance falls on the CML pre-driver while
  their drain capacitance falls on the 2.0 pF pad budget.
  **This remains the named fallback** if the cascode proves unworkable — but
  taking it means the swing spec must be re-derived under an explicitly
  degraded evidence standard, in a new decision record.
- **Uncascoded `nfet_03v3` switch pair straight to the pad.** Rejected: with
  the pad at the sink's AV_CC max of 3.465 V and the off-leg switch's source
  near ground, V_DS exceeds the 3.3 V rating continuously, not as a transient.
  It also puts the full switch drain capacitance on the pad node, and gives
  poor output resistance (return loss) for a circuit that is supposed to look
  like a current source.
- **`nfet_06v0_nvt` (native) cascode** for lower V_TH and more headroom.
  Rejected: L_min 1.8 µm, typical-model-only like the other 6 V devices, and
  the headroom problem it solves is not binding — with V_OL = AV_CC − 500 mV
  ≈ 2.6 V minimum at the pad, there is ample room over a standard cascode.
- **On-chip resistor as the I_TAIL reference.** Rejected: poly-resistor
  process spread exceeds the ±10% that V_SWING compliance allows, and the
  trim range needed to cover it would be large enough that the trim, not the
  reference, would be setting the current — which is a calibration
  requirement at test, not a specification.
- **Bandgap-referenced current with an on-chip resistor.** Rejected here for
  scope: it makes the block depend on a voltage reference this repo has not
  specified, and the resistor spread problem above is unchanged. The external
  resistor costs one pad and removes the dependency.
- **Add pre-emphasis / de-emphasis.** Rejected as premature: at 720p60 the
  channel budget in `tmds-tx.md` §7 shows ISI is negligible (13.5 τ of
  settling per UI). Pre-emphasis would add a second current DAC on the pad
  node, spending exactly the capacitance the budget cannot spare, to fix a
  problem that does not exist at the target rate.

## Consequences

- The block needs a cascode bias generator that holds V_BIAS_CASC across PVT
  such that the switch drains stay under 3.3 V at the pad's maximum *and* the
  cascode stays saturated at V_OL. That is a small circuit, but it is a
  circuit, and it is on the critical path for the driver issue.
- Power-up, power-down, and the unpowered state need explicit analysis: the
  pad may be held at 3.465 V by the sink while this block's AVDD_TMDS is at
  0 V. The cascode's gate bias is undefined in that state, and the ESD path
  ([0006](0006-pad-cell-and-esd-strategy.md)) is the only thing defining the
  pad node. This must be a named testbench, not an assumption.
- ≈112 mW of the block's ≤250 mW budget is DC dissipation in the four output
  stages, sourced from the sink. It does not scale down with data rate and is
  present whenever a link is up.
- One extra pad (`IREF_EXT`) and an external 1 kΩ ±1% resistor become part of
  the block's application requirements — a board-level obligation, recorded
  in `tmds-tx.md` §3 and §8.
- The missing 6 V corners (`tmds-tx.md` §10, O-3) remain a permanent gap in
  this block's evidence. This decision confines them to one common-gate
  device; it does not eliminate them.
