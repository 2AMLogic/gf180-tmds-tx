# DR-0003 custom final 2:1 (DDR) multiplexer sizing derivation

Companion to `design/cml-driver-sizing.md`, same discipline: every number
below is either taken from a spec/decision record, taken from the vendored
PDK's own published data, or a value this cell's own committed netlist
(`design/netlist/tmds_final_mux.spice`) and a direct ngspice operating-point
check reproduce — cited as such rather than presented as if derived in the
abstract. Issue #159.

## 0. Interface and topology

Ports, per `design/tmds_final_mux.sym` / `design/tmds_final_mux.sch`:

| Pin | Direction | Function |
|---|---|---|
| `D0P`/`D0N`, `D1P`/`D1N` | in | The two 2-bit-word halves the synthesized 10:1→2:1 reduction stage (`rtl/tmds_serializer.v`, DR-0014) presents — `D0` selected while `CLKP` is high, `D1` while it is low. Driven from an ideal differential source at THIS cell's own target output levels in verification (§5); the reduction stage's real analog output is a follow-on measurement, not modelled here. |
| `CLKP`/`CLKN` | in | DR-0012 Decision 1's internally-derived half-rate DDR clock (371.25 MHz @ 720p60, 135 MHz @ 480p). The divider is a follow-on cell; this cell only consumes its output. |
| `OUTP`/`OUTN` | out | Differential full-rate output, driving the CML driver's `INP`/`INN` gates directly — same 3.3 V domain (DR-0002/DR-0003), no level shifter. |
| `VDD` | in | 3.3 V core rail. Unlike the open-drain CML driver (`design/cml-driver-sizing.md` §0), this stage is **resistively loaded**, so it owns a supply pin the driver does not. |
| `VSS` | inout | Cell ground, and the body terminal of every device and every poly resistor (no isolated well — same NMOS/resistor-only convention as the driver). |

Topology (`design/netlist/tmds_final_mux.spice`, `XRC`/`XRLP`/`XRLN`/`XRREF`/
`XMU0P`/`XMU0N`/`XMU1P`/`XMU1N`/`XMCP`/`XMCN`/`XMT`/`XMB`): a clock-steered
lower differential pair (`MCP`/`MCN`) routes the tail current into one of
two upper data pairs (`MU0*` selected while `CLKP` is high, `MU1*` while it
is low), which share one pair of load resistors (`RLP`/`RLN`) returned to
`VDD` through a common series resistor `RC`. This is a resistively-loaded
CML 2:1 selector, current-steered on both the data axis (which pair) and,
within a pair, the differential axis (which leg) — the DDR behaviour comes
entirely from `CLKP`/`CLKN` toggling which data pair's current path is live,
not from any sequential state in this cell.

The tail current is **self-biased**: `RREF` (same resistor type as
`RC`/`RLP`/`RLN`) sets a reference current from `VDD` into a diode-connected
device (`MB`), mirrored 1:20 onto the tail device (`MT`) — the same 1:20
ratio `design/cml-driver-sizing.md` §1.3 uses, and the same device geometry
for `MT`/`MB` (`W=20u`/`nf=10`/`L=0.5u`, `m=20`/`m=1`). Unlike the driver,
there is no `IBIAS` port here: the reference is generated entirely inside
this cell.

Every active device is `nfet_03v3` (gf180mcu's 3.3 V core NMOS, DR-0002);
every resistor is `ppolyf_u` (unsilicided p+ poly, gf180mcu's own naming).

## 1. Output level targets (from DR-0003 / the cml-driver-sizing chain)

`design/cml-driver-sizing.md` §4.1 states, as a requirement levied on this
cell (not measured there — this record is where it is derived and, in §6,
checked): single-ended `vih = 0.85×VDD`, `vil = 0.55×VDD` (differential
swing `0.30×VDD`, common mode `0.70×VDD`), so that the driver's own
switch-pair sizing (which assumes this input swing is actually delivered)
is self-consistent. At the nominal 3.3 V digital rail: `vih = 2.805 V`,
`vil = 1.815 V`, swing `= 0.99 V`, common mode `= 2.31 V`.

## 2. Load-network derivation (steady-state, one leg conducting)

In steady state exactly one of the two upper pairs is selected (by
`CLKP`/`CLKN`) and, within that pair, exactly one leg conducts the full
tail current `I_tail` (the differential input is assumed to fully commute
it — §4). `RC` is in series with **both** legs (it carries `I_tail`
regardless of which leg is active), while each `RLP`/`RLN` carries current
only when its own leg is the active one:

```
V(TOP)              = VDD - I_tail * RC          (constant, both legs)
V(inactive leg)      = V(TOP) = VDD - I_tail*RC    = VIH  (high level)
V(active/conducting leg) = V(TOP) - I_tail*RL = VDD - I_tail*(RC+RL) = VIL  (low level)
swing = VIH - VIL = I_tail * RL
```

Solving §1's targets against a `10 mA` tail current (`design/cml-driver-
sizing.md` §1.3/§2's own target, reused here rather than re-derived, since
this cell shares the driver's tail-current window per §6 below):

```
RC = 0.15*VDD / I_tail = 0.15*3.3 / 0.010 = 49.5 ohm   (target)
RL = 0.30*VDD / I_tail = 0.30*3.3 / 0.010 = 99.0 ohm   (target)
```

Committed netlist values (`ppolyf_u`, `rsh = 350 ohm/sq` at the nominal
`res_typical` corner — `sm141064.ngspice`'s own `.LIB res_typical`):

| Resistor | `r_width` | `r_length` | `R = rsh * length/width` (typical) |
|---|---|---|---|
| `RC` | 20 µm | 2.65 µm | 46.375 Ω |
| `RLP`/`RLN` | 20 µm | 5.66 µm | 99.05 Ω |
| `RREF` | 2 µm | 24.8 µm | 4340 Ω |

`RL` matches its 99.0 Ω target to within 0.05 %. `RC` (46.375 Ω) sits about
6.3 % below its 49.5 Ω target — expected, not an error: `RC`'s actual
operating current is set by the self-biased reference (§3), not assumed
exactly 10 mA a priori the way this section's target arithmetic does; the
real operating point is verified directly below rather than forced to match
the hand estimate.

**Verified DC operating point** (`ngspice -b`, `.op` on the committed
`tmds_final_mux` subcircuit in isolation, `typical`/27 °C, `D0` side
statically selected, reproducible from `sim/dut/tmds_output_stage.spice`
plus a static-input testbench matching `sim/tmds-final-mux-eye/testbench/
tmds_final_mux_eye.spice`'s own `_z` DC copy):

| Quantity | Value | vs. §1 target |
|---|---|---|
| `I_tail` (measured, `-i(vdd)`) | 9.904 mA | target 10 mA, −0.96 % |
| `VIH` (`v(outn)`, inactive leg) | 2.8055 V | target 2.805 V (0.85×VDD), **+0.02 %** |
| `VIL` (`v(outp)`, active leg) | 1.8137 V | target 1.815 V (0.55×VDD), −0.07 % |
| Swing | 0.9918 V | target 0.99 V (0.30×VDD), +0.18 % |
| Common mode | 2.3096 V | target 2.31 V (0.70×VDD), **+0.02 %** |

The self-biased design lands within a few tenths of a percent of every §1
target at the nominal corner — closer than the simple hand estimate above,
because the actual loop (reference current through `RREF` and the 1:20
mirror) sets `I_tail` to whatever value makes `RC`'s own drop land at the
target, rather than the other way around. §6 (`sim/tmds-final-mux-eye/`)
is where this is checked across the full PVT matrix, not just this one
static corner.

## 3. Process invariance: a resistor RATIO, not a resistor VALUE

`RREF` is the **same resistor type** (`ppolyf_u`) as `RC`/`RLP`/`RLN`. Every
one of these resistors' value is `R = rsh_ppolyf_u * (r_length/r_width)`,
so a process corner that moves `rsh_ppolyf_u` (the vendored PDK ships
`res_typical`/`res_ss`/`res_ff` at 350/420/280 Ω/sq — a ±20 % spread) moves
**every** resistor in this cell by the same multiplicative factor. To first
order (treating the diode-connected reference's own gate-source drop as
process-invariant, which it is not exactly — see below):

```
I_ref  = (VDD - Vgs) / RREF  =>  I_ref  ~ 1/rsh   (RREF ~ rsh)
I_tail = 20 * I_ref                ~ 1/rsh
VIH    = VDD - I_tail * RC         ~ (1/rsh) * rsh = rsh-INVARIANT
swing  = I_tail * RL               ~ (1/rsh) * rsh = rsh-INVARIANT
```

The `rsh` dependence in the current and in the resistor multiplies to a
constant, because both the current-setting resistor (`RREF`) and the
level-setting resistors (`RC`/`RL`) are drawn from the same sheet. This is
why the design is self-biased from an in-cell reference of the *same*
resistor type rather than fed an externally-generated, fixed-value current
(as `design/cml-driver-sizing.md`'s `IBIAS` port is) — an externally fixed
`I_tail` would NOT cancel: `VIH = VDD - I_tail*RC` would move directly with
`RC`'s own ±20 % `rsh` spread, with nothing to cancel it.

**What this does not claim to cancel**: the diode-connected reference's own
`Vgs` (and therefore `I_ref`) still depends on `nfet_03v3`'s own process
corner (`ff`/`ss` mobility and threshold-voltage shifts), which is
independent of the poly sheet-rho corner — a `tt`/`ss`/`ff` *device*
process sweep is not the same axis as a `res_typical`/`res_ss`/`res_ff`
*resistor* sheet-rho sweep, and the vendored PDK's corner `.lib` sections
bundle a fixed pairing of both per named corner (`tt`, `ss`, `ff`, `fs`,
`sf` each select one FET corner and one matched passive corner — see
`sim/harness/corners.py`). This section's cancellation claim is
specifically about the **resistor-value** contribution to output-level
variation; the residual device-driven variation is exactly what §6's
PVT-swept simulation measures rather than assumes away.

## 4. Switch-pair sizing

### 4.1 Data pairs (`MU0*`/`MU1*`): reused from the driver's own derivation

`design/cml-driver-sizing.md` §4.2 derives `W=128u`/`nf=64`/`L=0.28u` as the
minimum practical NMOS switch-pair width for full current-steering
completeness (>99.9 % commutation) against a `10 mA` tail and this cell's
own assumed differential input swing (`0.30×VDD` ≈ 0.891–0.99 V across the
digital rail's ±10 % range) — the *identical* input-swing assumption this
cell's own §1 output targets state, because this cell's data pairs face the
same steering problem against the same swing as the driver's switch pair
faces from this cell's output. The committed netlist reuses that derivation
directly (`XMU0P`/`XMU0N`/`XMU1P`/`XMU1N`, `W=128u`/`nf=64`/`L=0.28u`,
byte-identical geometry to `design/cml_driver.sch`'s `XM1`/`XM2`) rather
than re-running the DC-sweep study for a second, functionally equivalent
switch pair.

### 4.2 Clock-steered pair (`MCP`/`MCN`): wider, because it is the binding commutation stage

`MCP`/`MCN` are `W=192u`/`nf=96`/`L=0.28u` — 1.5× the data pairs' width, at
the same tail current and the same minimum channel length. This pair steers
the *entire* tail current between the two data pairs' shared tail node,
using the clock's own swing (`vih_c = 0.60×VDD`, `vil_c = 0.30×VDD`, per
`sim/tmds-final-mux-eye/testbench/tmds_final_mux_eye.spice`'s input-model
section — a *smaller* differential swing, `0.30×VDD`, than the data pairs
see at their own gates once selected) — so, for the same commutation-vs-
input-swing relationship §4.1's DC-sweep study establishes (wider switch
needed for full commutation at a smaller available swing), the clock pair
is the one that would fall short of full commutation first if both pairs
were sized identically. Widening it by 1.5× is this cell's design margin
against that: not a re-run of §4.1's isolated per-candidate DC sweep for
this specific pair (deferred as optional future refinement — see
"Non-goals"), but a design choice §6's own `vswing_m`/`vswing_s` PVT-swept
measurement (word-alternating **and** clock-alternating stimulus, both
checked ≥ 0.8 V — the same full-commutation floor §4.1 measured) validates
end-to-end rather than in isolation.

## 5. Downstream/upstream self-consistency

This cell's own output-level targets (§1: `vih = 0.85×VDD`, `vil =
0.55×VDD`, common mode `0.70×VDD`) are **the same levels its own testbench
assumes for its input** (`sim/tmds-final-mux-eye/testbench/
tmds_final_mux_eye.spice`'s `vih_d`/`vil_d` parameters, driving `D0`/`D1`).
This is deliberate, not an arbitrary testbench convenience: it is what
makes the level specification **self-consistent across the chain** —

```
tmds_serializer (DR-0014) --[D0/D1 @ this cell's own output levels]-->
    tmds_final_mux --[OUTP/OUTN @ the SAME levels]--> cml_driver
```

— i.e. the synthesized reduction stage that drives this cell's `D0`/`D1`
inputs is assumed to be *built from a copy of this same cell* (or a
circuit presenting the same interface), so the level spec closes on itself
rather than needing a distinct, separately-derived level pair at every
stage of the chain. `sim/tmds-final-mux-eye/` is the first measurement of
whether the REAL cell actually delivers what its own testbench (and, by
this self-consistency argument, its own upstream neighbour) assumes;
`sim/cml-driver-eye-realmux/` is the second (the driver's own graded rows,
re-measured with this cell's real output substituted for the ideal source
`design/cml-driver-sizing.md` originally assumed).

The clock input (`CLKP`/`CLKN`) is *not* assumed to come from a copy of
this cell — it is DR-0012 Decision 1's divide-by-two output, a different
circuit with its own, separately-stated swing (`0.60×VDD`/`0.30×VDD`, §4.2)
and edge-rate (150 ps) assumptions, disclosed as such in the testbench
header rather than folded into this section's self-consistency claim.

## 6. Verification — `sim/tmds-final-mux-eye/` and `sim/cml-driver-eye-realmux/`

Both benches drive the real `tmds_final_mux` cell (`sim/dut/
tmds_output_stage.spice`, mechanically derived from the same xschem netlist
this document describes) into a real `cml_driver` instance's gate load —
`sim/tmds-final-mux-eye/` measures this cell's own output against §1's
targets plus the driver's §4.1 full-commutation floor (0.8 V differential,
`design/cml-driver-sizing.md` §4.2's own measured point); `sim/cml-driver-
eye-realmux/` re-measures the driver's own DR-0002 swing/common-mode/
jitter/device-stress rows with this cell's real output substituted for the
ideal source those rows previously assumed, across the same full PVT ×
bit-rate grid `sim/cml-driver-eye` uses.

**Status of this record's own citation of that evidence**: see each bench's
own `records/` directory for the corner matrix actually run and its
coverage against CLAUDE.md's full-PVT expectation — issue #159's PR body
states exactly which corners are covered by the record committed with it,
and names the remainder as explicit follow-on work where the full grid was
not reached (this repository's sandboxed build environment has no
OpenROAD/Docker access and shares its CPU with other concurrent sessions;
see those benches' own evidence records for the disclosed subset reason,
if any).

## 7. Non-goals (explicit, per this issue's scope)

- **An isolated DC-sweep commutation study for the clock-steered pair**,
  matching `design/cml-driver-sizing.md` §4.2's own per-candidate table for
  the data pairs, is not performed here — §4.2 above states the design
  choice and cites end-to-end PVT verification instead. Worth doing if a
  future record needs the clock pair's own margin quantified in isolation.
- **A dedicated bandwidth/dominant-pole analysis** at this cell's own
  output node (`design/cml-driver-sizing.md` §5's counterpart) is not
  performed here — this cell's real load (a real driver's gate
  capacitance, not a swept pad capacitance) is a different loading
  question from the driver's own pad-capacitance sweep, and is exactly
  what `sim/tmds-final-mux-eye/`'s `trise_m`/`tfall_m`/`vswing_n` (loaded
  vs. unloaded copy) rows measure directly rather than estimate
  analytically.
- **The reduction stage's own analog output** (what `rtl/tmds_serializer.v`
  /DR-0014's synthesized or custom implementation actually delivers to
  `D0`/`D1`) is modelled here as an ideal source at this cell's own target
  levels (§5) — measuring the REAL reduction-stage output against this
  cell's input assumption is future work this record does not perform (the
  720p60 operating point's own reduction stage is custom-domain per
  DR-0014 and does not exist as a drawn circuit yet).
- **Layout, DRC, LVS** for this cell are not addressed here — schematic
  and simulation only, per this issue's own scope.
