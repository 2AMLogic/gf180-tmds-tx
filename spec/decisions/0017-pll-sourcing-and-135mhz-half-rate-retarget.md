# DR-0017: PLL sourcing — the sibling is `gf180-pll`; retarget to a 135 MHz half-rate clock (480p first), 720p60 deferred with no clock path

**Status: Proposed.** Records the operator ruling on issue
[#194](https://github.com/2AMLogic/gf180-tmds-tx/issues/194) (2026-10-02,
path (b)). **This record is not ratified by editing this line.** Per the
two-key rule (`2AMLogic/2am#1056`) it is ratified through `2am`'s
`scripts/ratify-key.sh` with both `RATIFY-KEY` reviews; until then every
`spec/tmds-tx.md` edit that cites it takes effect only on that ratification.
Do not flip this Status to `Accepted` by hand.

## Context

`README.md` §Not in scope and `spec/tmds-tx.md` §2 / DR-0004 levied a
bit-rate clock of 742.5 MHz (720p60) / 270 MHz (480p) and a 27.000 MHz
reference on "a sibling canary" without naming it. The only gf180 PLL
canary is `gf180-pll`. Its ratified `spec/pll.md` (read at `gf180-pll`
`db7a0455bdfcf546f0501ee1e0606eca36d1e7fb`, origin/main, 2026-10-02) gives:

| `pll.md` row | Ratified | Against this block's old §2 |
|---|---|---|
| 1 Output band | 10-200 MHz (measured ceiling 247.8 MHz at `all-slow`/-40 C/3.63 V, unratified) | 270 MHz and 742.5 MHz both above the band |
| 2 Reference | **1-25 MHz**, CMOS, duty 30-70 % | 27.000 MHz is above the band |
| 3 Ratio | integer N = 4-64, static; no post-VCO divider | 742.5 MHz = 27 x 27.5 and every power-of-two submultiple are non-integer |
| 5 Period jitter | <= 1.0 % of period, RMS | a different quantity from this block's 0.10 UI pk-pk |
| 13 Duty | 45-55 % at `CLK` (measured 44.375-50.696 %, 7 of 90 points miss at the `lo` edge) | see Decision 4 |
| 14 Levels | rail-to-rail CMOS on `vdd_vco`, into <= 50 fF | §2/DR-0012 asked for differential low-swing |
| (outputs) | one output, `CLK` | §2 asked for a second, pixel-rate output |

Options on the issue: (a) extend `gf180-pll`'s band; (b) take a lower-rate
PLL clock and serialize at a lower internal rate; (c) a different source.

## Decision

**Path (b): this block retargets to what `gf180-pll` v1 serves.**

1. **Sibling named.** The PLL is `2AMLogic/gf180-pll`. `README.md`,
   `spec/tmds-tx.md` §2 and DR-0004 name it. This block still **does not
   design a PLL** (CLAUDE.md scope discipline is unchanged).
2. **Operating point.** 480p (720x480p60, 270 Mbps/lane) is the first and
   only operating point with a clock path. It is served by a **135 MHz
   half-rate clock**: 135 MHz = 270 Mbps / 2, one integer ratio inside
   `pll.md` row 1's ratified 10-200 MHz band, with no local clock
   multiplication.
3. **720p60 is deferred, with no clock path.** 742.5 Mbps needs a
   371.25 MHz half-rate clock (or 742.5 MHz full-rate). `gf180-pll` v1 cannot
   produce either: 371.25 MHz is above the 200 MHz band, and from a 27 MHz
   system reference 742.5/371.25/185.625/92.8125 MHz are N = 27.5/13.75/
   6.875/3.4375, all non-integer, the last below N-min. No other clock source
   is named. The 720p60 rate numbers in `spec/tmds-tx.md` are **kept as the
   deferred target's definition**, not as a live interface. Reviving 720p60
   needs a successor record that names a clock path (a `gf180-pll` v2 band and
   ratio scheme, or another named source under `2am/REUSE.md` §Adopt or
   record). 1080p60 remains a stretch that does not drive architecture
   (DR-0001); it is unaffected and equally without a clock path.
4. **Interface is reduced to what the supplier has.** The PLL levies on
   `gf180-pll` are now exactly: one `CLK` output at **135 MHz**, single-ended
   rail-to-rail CMOS (its row 14), 45-55 % duty (its row 13), loaded by this
   block with one clock-input pin per DR-0012 Decision 4. The reference
   input is **13.5 MHz** (see Decision 5). No second (pixel) output, no
   differential output.
5. **Reference is 13.5 MHz, N = 10; the ruling's "27 x 5" is not usable
   as written.** The issue's constraint math (135 = 27 x 5) uses a 27 MHz
   reference, which is above `pll.md` row 2's ratified 1-25 MHz range (the
   `gf180-pll` spec itself records this mismatch). The same 135 MHz is reached
   with an in-range reference as 13.5 MHz x N = 10 (N inside row 3's 4-64).
   13.5 MHz is the 27.000 MHz system clock divided by 2, which this block
   provides with one toggle flip-flop (exactly 50 % duty, within row 2's
   30-70 %); the 27.000 MHz clock remains this block's own reference source.
   This is a choice made inside the ruling's intent and is **flagged for the
   two ratifying reviews**; alternatives within range (22.5 MHz x 6,
   9 MHz x 15, ...) are not excluded. `gf180-pll`'s loop-bandwidth/Icp trim
   rule for f_ref = 13.5 MHz (the 8 MHz row's code, "nearest tabulated at or
   below") is `gf180-pll`'s to confirm; this block does not restate it.
6. **Re-derivation of DR-0012 and DR-0014 for the 135 MHz half-rate scheme**
   (the changes below are the *only* edits this record authorizes to those
   decisions; every other row of DR-0012/DR-0014 stands as ratified):
   - **DR-0012 Decision 1 (internal ÷2): superseded.** There is no ÷2 stage.
     The PLL's 135 MHz output **is** the half-rate DDR clock (the final 2:1
     mux samples both of its edges: 2 x 135 = 270 Mbps) **and** the
     synthesized-domain clock (5 x pixel clock). The identity DR-0012 used
     (half-rate = 5 x pixel) still holds: 135 MHz = 5 x 27.000 MHz.
   - **Pixel clock is derived internally, not levied.** The 27.000 MHz
     pixel clock is **135 MHz ÷ 5** (a 5-state counter in this block),
     replacing §2's pixel-rate PLL output and the "edge-aligned 10:1 pair"
     clause: both clocks now come from one 135 MHz root, so alignment holds by
     construction, with no cycle slips. The counter phase relative to the
     27 MHz system reference is not defined and need not be: the TMDS sink
     recovers its clock from this block's own clock channel, and the
     upstream data source is clocked from this block's pixel-clock output
     (interface detail for the top-level work, not fixed here).
   - **DR-0012 Decision 2 (signal type): bit-rate-clock row replaced.**
     The 135 MHz clock arrives single-ended CMOS (`pll.md` row 14); any
     single-ended-to-CML conversion for the custom mux/driver is this
     block's input stage, not a PLL requirement. The "differential, 300-800
     mV" row was `Proposed` and never measured against any PLL; it is
     withdrawn. The pixel-rate output row is withdrawn (Decision 6, above).
   - **DR-0012 Decision 3 (duty): its payoff is reversed.** DR-0012 moved the
     one duty-critical (both-edge) clock onto an internal ÷2 that is 50 %
     by construction. That divider is gone, so the DDR stage now samples
     both edges of a PLL clock whose duty is 45-55 % (`pll.md` row 13), and
     the measured 44.375 % minimum misses its own 45 % line at 7 of 90
     points. At 135 MHz, 1 % of duty = 74 ps = 0.02 UI of 270 Mbps, so a
     +/-5 % duty error alone is +/-0.10 UI of unequal-UI width on alternate
     bits. This is a **new, un-budgeted deterministic jitter term** that
     DR-0004's 0.25/0.10/0.15 UI split does not contain. This record does
     **not** relax that split. It records the term as an **open item**
     owned by this block (candidates: a duty-cycle corrector local to the
     clock input stage, or a local ÷2/2x scheme, which would be a clock
     multiplier and is **not** authorized here), to be closed by a
     measured follow-up before the 0.15 UI allocation is claimed met.
   - **DR-0004 jitter.** The 0.25 UI total, 0.10 UI PLL allocation and
     0.15 UI remaining split stand unchanged, at the 480p numbers
     (270 Mbps UI = 3.704 ns: 0.10 UI = 370 ps pk-pk, referenced to either
     edge of the 135 MHz clock, i.e. TIE per edge). `gf180-pll` ratifies
     period jitter <= 1.0 % RMS (row 5), not a pk-pk TIE bound, and has no
     closed-loop jitter measurement at 135 MHz recorded as a pk-pk figure;
     **the PLL-attributable allocation is therefore not shown to be met**
     and stays an unmet cross-block obligation, not a pass. The "informative
     RMS approximation" (9.6 ps RMS @ 742.5 Mbps) is a deferred-720p60 number;
     at 480p it scales to about 26 ps RMS (370 ps / 14.1), informative only.
   - **DR-0014 (serializer).** Its 720p60 finding (reduction cannot close
     timing in the synthesized domain at 371.25 MHz; moves to the custom
     domain) is **unchanged and now dormant**, applying only if 720p60 is
     revived. Its 480p result (135 MHz: feasible with comfortable margin,
     synthesized-domain assignment of DR-0003 stands) is now **the live
     case and the only operating point**: the premise "135 MHz = the
     internal ÷2 of the 270 MHz clock" becomes "135 MHz = the PLL output
     directly". The measured timing arcs and the loadable-shift-register
     micro-architecture do not depend on where the 135 MHz comes from.
     DR-0003's synthesized/custom boundary at 480p stands unmodified.
7. **Reuse record.** `reuse.lock.json` pins the consumed `gf180-pll`
   interface (band 10-200 MHz, output 135 MHz, reference 13.5 MHz, N = 10) to
   the `gf180-pll` commit above and the sha256 of `spec/pll.md` at it. It
   stamps the sibling's ratified spec (the contract), not silicon or layout
   bytes; there are none to import yet.

## Alternatives considered

- **(a) Extend `gf180-pll` to a v2 (band and ratio scheme)** keeps §2's
  742.5 MHz numbers but lands a v2-scale redesign on the sibling: 742.5 MHz
  is about 3.7x its ratified ceiling and needs fractional-N or a post-VCO
  divider. Not chosen: it does not close with existing ratified silicon. It
  stays the natural route if 720p60 is revived.
- **(c) A different clock source.** None named; would trigger `2am/REUSE.md`
  adopt-or-record and a `repos.yml` `consumes` change. Not chosen.
- **(b'), local multiplication/serialization from a lower PLL clock** (the
  issue's literal (b)). It is a PLL/DLL design and would relax the ratified
  "do not design a PLL here" scope; rejected. The ruling's (b) is the narrower
  form adopted above: no multiplication, half-rate directly.
- **Quarter-rate or lower-rate serialization** (e.g. 67.5 MHz) was not
  adopted; 135 MHz is the one rate already inside the band with an in-range
  reference, and DR-0014 measured it.

## Consequences

- 480p is the sole operating point with a clock path; no 720p60 claim can be
  made against this interface. 720p60 stays in `spec/tmds-tx.md` as the
  deferred target (DR-0001's ordering of rates is not otherwise changed).
- The PLL interface shrinks to one 135 MHz CMOS output and a 13.5 MHz
  reference, both inside `gf180-pll`'s ratified rows 1-3, 13, 14.
- Open items carried, none relaxed: the duty-cycle jitter term (Decision 6),
  the unshown PLL-attributable pk-pk jitter (Decision 6), and the reference
  choice (Decision 5). Each must be closed by measurement before the 480p
  jitter budget is claimed.
- This block's RTL will need a ÷5 pixel-clock counter and a ÷2 reference
  divider in place of DR-0012's ÷2; that work is not authorized by this
  record. No RTL, schematic, layout, or recorded evidence is modified.
- `gf180-pll#465` carries the supplier-side outcome (comment text in the
  PR for this record); this repository does not post to that tracker.

## Status

**Proposed**, pending the `ratify-key.sh` two-key ratification described at
the top of this record. Cross-references: issue #194; `gf180-pll#465`;
`2am/REUSE.md`; `2am#1056`; DR-0001, DR-0003, DR-0004, DR-0012, DR-0014.
