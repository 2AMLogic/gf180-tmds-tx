# 0001 — Resolution ladder, and the standing of 1080p60

**Status:** Accepted 2026-08-05.

## Context

The repo README's DRAFT table (commit `fc8c465`) named 720p60 as the target,
480p as the fallback, and 1080p60 as a stretch, but did not say what
"stretch" *obliges* — which is the part that matters, because a stretch mode
that quietly influences early decisions is indistinguishable from a
requirement.

The three modes differ by 5.5× in bit rate. At 180 nm the difference is not
cosmetic: 1080p60 needs a 742.5 MHz custom clock domain and (see
[0005](0005-pll-interface-and-jitter-budget.md)) roughly a 2× tighter PLL,
because random jitter is fixed in picoseconds while the UI halves. If the
1080p60 numbers are allowed into the budgets, the PLL requirement levied on
the sibling block doubles in difficulty for a mode this block is not
promising.

Pixel clocks also have to be *reachable* from a single reference. Exact-rate
CEA-861 timings:

| Format | Total pixels × lines × rate | Pixel clock |
|---|---|---|
| 720×480p59.94 | 858 × 525 × 59.94 | 27.000 MHz |
| 1280×720p60 | 1650 × 750 × 60 | 74.250 MHz |
| 1920×1080p60 | 2200 × 1125 × 60 | 148.500 MHz |
| 640×480p60 (DVI failsafe) | 800 × 525 × 59.94 | 25.175 MHz |

The first three are `×1`, `×11/4`, and `×11/2` of 27.000 MHz. The fourth is
not an integer ratio of anything the first three share.

## Decision

1. **720p60 (1280×720p60, 74.250 MHz pixel, 742.5 Mbps/lane) is the target.**
   It is the only mode that appears in a signoff gate.
2. **480p (720×480p59.94, 27.000 MHz pixel, 270 Mbps/lane) is the guaranteed
   fallback.** Note the frame rate: 27.000 MHz is the 59.94 Hz variant, not
   60 Hz.
3. **1080p60 (148.500 MHz pixel, 1485 Mbps/lane) is a stretch mode with no
   standing.** Concretely, and bindingly:
   - No architectural choice may be made *because* of 1080p60 while 720p60
     is unclosed.
   - No 1080p60 number may appear in any budget levied on another block —
     in particular not in the PLL requirement.
   - No signoff gate may reference 1080p60.
   - Taping out with 1080p60 failing is an acceptable outcome.
4. **`÷1.001` (59.94/60 Hz cross) variants are not supported**: 720p59.94
   (74.1758 MHz) and 480p60 (27.027 MHz) are out.
5. **640×480p60, the DVI failsafe mode, is not supported.** This block does
   not claim DVI failsafe conformance.

## Alternatives considered

- **Make 1080p60 a soft requirement ("design for it where cheap").** Rejected:
  "where cheap" has no test. The one place it would have bitten immediately
  is the PLL jitter number, where honoring 1080p60 would have doubled the ask
  on the sibling block for a mode we are not promising. A stretch goal that
  can move another block's requirement is not a stretch goal.
- **Support 640×480p60 for DVI failsafe conformance.** Rejected: 25.175 MHz
  is not an integer ratio of 27.000 MHz, so it forces either fractional-N
  synthesis or a second reference oscillator — see
  [0002](0002-reference-clock-and-clock-mastership.md). The cost lands
  entirely on the sibling PLL block, for a mode no part of this canary's
  purpose requires. Recorded as a known non-conformance rather than absorbed.
- **Support the 59.94 Hz variants of 720p.** Rejected for the same reason,
  and with less to gain.
- **Make 480p the target and 720p the stretch.** Rejected: 270 Mbps is
  comfortably inside what standard cells alone could serialize at this node,
  which would remove the CML driver and the pad-ring problem — the two things
  this canary exists to exercise.

## Consequences

- The block is a fixed-timing transmitter for three specific formats, not a
  general video interface. Any arbitrary-timing capability is a new decision.
- The PLL requirement ([0005](0005-pll-interface-and-jitter-budget.md)) is
  written against 720p60 only, and explicitly states what 1080p60 *would*
  have cost so the omission is visible rather than accidental.
- The partition in [0003](0003-serializer-partition.md) does scale to
  1080p60 without restructuring. That is an incidental property and is
  recorded as such — it must not be cited later as evidence that 1080p60 was
  in scope.
- A future 640×480p60 or 59.94 Hz requirement would supersede this record and
  [0002](0002-reference-clock-and-clock-mastership.md) together.
