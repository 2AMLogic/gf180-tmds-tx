# DR-0016: The DVI-mode framing stands; HDMI data islands sit outside this block's boundary

**Status: Proposed.** Records a scope/framing answer only. No parameter in
`spec/tmds-tx.md` §1 changes, no RTL or analog work is authorized or
required by this record, and `CLAUDE.md` is not amended by it.

## Context

Issue [#185](https://github.com/2AMLogic/gf180-tmds-tx/issues/185) asks this
repository to re-check its own DVI-mode-only framing after a product-side
decision it does not own.

**What changed, on the product side.**
[`2AMLogic/product#16`](https://github.com/2AMLogic/product/issues/16)
(closed, operator ruling 2026-09-15) decided **audio in, one chip for both
dongle products**. `2AMLogic/product`'s `dongle/dongle-family.md` § "Audio:
in, on one chip (decided 2026-09-15)" propagates the consequence in its own
words:

> **Digital block scope.** The TMDS path grows from DVI-mode video-only to
> genuine HDMI: data-island packet formatting (audio samples, the audio
> InfoFrame, and ACR — audio clock regeneration packets) now sits between an
> ADPCM audio decoder and the TMDS encoder in the block diagram above.

and, on this repository specifically:

> **`gf180-tmds-tx` relationship.** […] Per this repo's convention (README →
> "What lives here versus elsewhere"), the design lives in the canary repo
> and the decision lives here, so the framing re-check itself was filed as a
> cross-repo issue […] rather than edited directly from this repo.

`2AMLogic/product`'s `everyblock/block-matrix.md` 2026-09-15 decision-log row
says the same thing from the other side — "This table does not resolve that
— the design lives in the canary repo" — and explicitly narrows what is open:

> The ATC/licensing-fee conclusion itself is unaffected either way: the HDMI
> Adopter Agreement fee covers the connector and trademark regardless of
> data-island content (`dongle-family.md`'s Licensing section), so nothing
> above needs correcting on that point — only the "DVI-mode" scope premise is
> now pending re-check.

So the product decision is settled and is **not** re-litigated here; what is
open, and what this record answers, is a boundary question this repository
owns.

**What is at stake on this side.** The DVI-mode framing is written into two
load-bearing documents, not just README prose:

- `spec/tmds-tx.md:11-14` (**RATIFIED 2026-08-05**): "This block is a
  **DVI-mode TMDS transmitter**. TMDS/DVI signaling is unencumbered; the HDMI
  Adopter Agreement covers only the connector and trademark. Nothing in this
  repository is HDMI-certified, HDMI-branded, or should be described as an
  HDMI block."
- `CLAUDE.md` § "On HDMI, and what may be said": "This block is therefore a
  **DVI-mode TMDS transmitter**. Do not describe it as an HDMI block, do not
  use the HDMI trademark or logo in this repo, and do not imply any HDMI
  certification or compliance."

**What this block actually is, structurally** — the fact the boundary answer
turns on. The block is already built as a chain with a **10-bit-character
cut** in the middle of it:

```
rtl/tmds_encoder.v  --[10-bit character @ pixel rate]-->  rtl/tmds_serializer.v
   --[2 bits @ half rate]-->  design/tmds_final_mux.sch  --[1 bit @ bit rate]-->
   design/cml_driver.sch  -->  pad (DR-0011)
```

`rtl/tmds_encoder.v` implements DVI 1.0 §3.3's two-stage algorithm and its
four control characters, cited to the public DVI 1.0 text. Everything
*downstream* of that cut — the serializer, the custom 2:1 final mux, the CML
driver, the pad and its ESD network — is **character-agnostic**: it moves
10-bit words, and DR-0003/DR-0012/DR-0014 define it that way without any
reference to what produced them. The block-level top that binds these
together is not itself ratified yet (DR-0014 leaves which domain implements
the reduction rate-dependent, and
`verification/tmds_serializer/tmds_tx_chain.v` states plainly that its own
wrapper "is a bench fixture… nothing here should be mistaken for a ratified
top-level netlist").

HDMI audio needs two layers this block does not have, and they are not the
same kind of thing:

- a **packet layer** — audio sample packets, the audio InfoFrame, ACR,
  packet header/parity, and the scheduling that fits them into blanking;
- a **character layer** — the data-island coding (TERC4), the guard-band
  characters that bracket an island, the preambles that announce it, and the
  period state machine that switches between video, control and island
  periods.

The packet layer is unambiguously upstream digital work. The character layer
is *not* something a block placed upstream of a DVI 8b/10b encoder can
produce by feeding it pixel bytes — an 8b/10b video encoder has no input that
emits a guard-band or TERC4 character. Any workable Option-A split therefore
has to join this block at the **character** boundary, not at the pixel-byte
input. That distinction is what the rest of this record is about.

## Decision

**Option A: this block stays a DVI-mode TMDS transmitter. Data-island packet
formatting, the audio InfoFrame, ACR, and the TERC4/guard-band/preamble
character layer all live outside its boundary, in the consumer's digital
block (or a separate canary), and join this block at the existing 10-bit
character cut.**

Answering issue #185's three questions explicitly:

### 1. Is "unencumbered DVI-mode signaling" still the right framing?

**Yes, unchanged.** `spec/tmds-tx.md:11-14` and `CLAUDE.md` § "On HDMI, and
what may be said" are accurate as written and are **not** amended by this
record.

The framing describes what *this block* encodes and what *this repository*
claims — not what a chip that integrates it ultimately emits. Under this
decision, the only encoder in this repository remains `rtl/tmds_encoder.v`,
which implements DVI 1.0 §3.3 and nothing else; no HDMI-defined character,
packet, or period behavior is designed, described, or claimed here. A
downstream integrator emitting HDMI through a character-agnostic serializer
and driver does not make this block's own description wrong, any more than
the PLL living in a sibling canary makes this block's §2 interface contract
a PLL design.

The framing would only need to change under Option B (below), which is
rejected.

### 2. Does the licensing conclusion still hold?

**Yes — and this record does not re-derive it; it cites the analysis that
already settled it.** `2AMLogic/product`'s `everyblock/block-matrix.md`
2026-09-15 row states the ATC/licensing-fee conclusion is "unaffected either
way," because "the HDMI Adopter Agreement fee covers the connector and
trademark regardless of data-island content"
(`dongle/dongle-family.md`'s Licensing section). The 2026-08-11 finding —
ATC is a first-of-type obligation on a finished Licensed Product, not on a
standalone IP block unless the block itself claims HDMI compliance — had its
*premise* re-checked by issue #185, not its conclusion, and this record
re-affirms the premise rather than disturbing it.

What does move is the product-level **conformance test surface**, which
`dongle-family.md` records as growing to cover audio packet formatting and
ACR. That is the dongle's line item, not this block's, and is recorded here
only so that nobody later mistakes it for an obligation this repository
inherited.

One consequence worth stating in this repository's own terms: Option A keeps
every normative source cited in this repository **publicly citable**.
`rtl/tmds_encoder.v` cites DVI 1.0 §3.3 for its algorithm and character
values, with a public cross-check. The TERC4 code table, guard-band
characters, preamble encodings, and packet ECC are defined normatively in the
HDMI Specification, which is not distributed on those terms. Keeping that
layer outside this repository keeps its evidence chain — "no claim without a
testbench", every number traced to a citable source — intact without needing
a judgement call about what may be transcribed.

### 3. Does data-island/InfoFrame/ACR formatting belong in this block?

**No — both layers belong outside it, and they join at the 10-bit character
cut that already exists.**

- **Packet layer** (audio sample packets, audio InfoFrame, ACR, header/ECC,
  scheduling) — outside. This matches where `dongle-family.md`'s own block
  diagram already puts it: "between an ADPCM audio decoder and the TMDS
  encoder". Nothing about it is process-, PDK-, or pad-specific; it is
  portable RTL with no reason to be tied to a gf180mcu analog canary.
- **Character layer** (TERC4, guard bands, preambles, period state machine) —
  also outside, for the reasons in §"Alternatives considered" below, but with
  the interface consequence that it must emit finished 10-bit characters
  rather than pixel bytes.

**Interface requirement this decision levies on this block** (an integration
interface, not a scope expansion): the eventual block-level top must admit,
per lane, an externally supplied 10-bit character per pixel clock and a
select between it and `rtl/tmds_encoder.v`'s own output. That is a mux and a
port list at a cut point the design already has; it adds no HDMI-defined
content to this repository and changes no parameter in §1. Because the
block-level top is not ratified yet (see Context), this is a requirement on
the top when it is defined, not a retrofit of anything already ratified. It
is tracked as a follow-up, contingent on this record being accepted — not
performed by issue #185.

## Alternatives considered

- **Option B — expand this block's scope to include data-island
  packetization, the audio InfoFrame, ACR, and the TERC4/guard-band character
  layer.** Rejected, on four grounds, none of which is "it cannot be done":

  1. **It requires amending ratified text and this repository's own agent
     instructions.** `spec/tmds-tx.md:11-14` would need its "This block is a
     **DVI-mode TMDS transmitter**" sentence and its "Nothing in this
     repository is HDMI-certified, HDMI-branded, or should be described as an
     HDMI block" sentence revised, plus a new §1 row or section for the
     packet/island path. In `CLAUDE.md` § "On HDMI, and what may be said",
     two specific sentences would need revision — "This block is therefore a
     **DVI-mode TMDS transmitter**." and "Do not describe it as an HDMI
     block, do not use the HDMI trademark or logo in this repo, and do not
     imply any HDMI certification or compliance." (the section's first
     sentence, on TMDS signaling being unencumbered and the Adopter Agreement
     covering connector and trademark, would **not** need revision — see
     question 2). That is a human/Champion ratification act, not something a
     builder or this record can self-grant, and it should not be spent unless
     the engineering case demands it. It does not.
  2. **It imports normative content this repository cannot cite publicly.**
     See question 2 above. Every character table in this repository today
     traces to public DVI 1.0; the HDMI equivalents do not have a comparable
     public normative source.
  3. **It competes with the thing this canary exists to test.** `CLAUDE.md`
     is explicit that "the pad ring is the point, and the risk," that 720p60
     is the target, and that sibling-canary work stays in its sibling ("The
     PLL comes from a sibling canary. Do not design one here."). A packet
     assembler, its ECC, and an audio clock-domain crossing are portable
     digital design with no bearing on whether a drawn pad cell, its ESD
     network, and a CML driver close 720p60 — the open question this block
     was created to answer. Absorbing them would grow the review surface of
     the riskiest block in the program for no gf180mcu-specific return.
  4. **It is not where the product repository itself puts the work.** The
     dongle's own block diagram already places packet formatting in its
     digital block ahead of the TMDS encoder, and its audio-in entry budgets
     that work as the dongle's ("real digital design work beyond the video
     decode path already budgeted"). Option B would move work the consumer
     has already scoped for itself into its supplier.

  Option B is not rejected as wrong in principle. If a real integration finds
  the character-boundary interface insufficient — for example if island
  timing turns out to need visibility into serializer state that cannot be
  exposed cleanly — a future record may supersede this one. That would be a
  finding, not a preference.

- **Option A-strict — keep this block untouched with no character input at
  all, and have the wrapper carry its own serializer and driver.** Rejected.
  It duplicates exactly the expensive, already-measured parts of this block
  (the 10:1→2:1 reduction, the custom final mux, the CML driver, the pad and
  ESD network — DR-0011/DR-0014 and the PVT evidence in
  `measurements/characterization.md`), and two transmit paths cannot share one
  pad. The character cut already exists in the design; refusing to expose it
  buys nothing and costs a second analog implementation.

- **Rename or re-badge the block** (for example as an "HDMI-capable TMDS
  transmitter") **while leaving its contents DVI-mode.** Rejected as both
  inaccurate and precisely the association `CLAUDE.md` forbids: it would imply
  a compliance relationship this block neither has nor is verified against,
  for no engineering change whatsoever.

- **Do nothing — leave the framing unreconciled and let it be settled by
  whichever PR arrives first.** Rejected; that silent-drift risk is exactly
  what issue #185 was filed to prevent. The cost of this record is one file;
  the cost of not having it is a future PR growing island support inside this
  block without the ratified spec, the compliance language, or the block
  boundary ever being reconciled.

## Consequences

- **Nothing in the ratified spec changes.** `spec/tmds-tx.md` §1's parameter
  table, §2's PLL interface, §3's pad/ESD strategy, and its lines 11-14
  framing all stand exactly as ratified. `CLAUDE.md` is unchanged, and
  `README.md` is unchanged. No RTL, schematic, layout, or verification
  artifact is added or modified by this record.
- **On ratification** (`Status: Accepted`), one editorial follow-up is
  required that issue #185 deliberately does not perform: an index entry for
  this record under `spec/tmds-tx.md` § "Further decision records (index)",
  per `spec/README.md`'s convention that DR-0010-onward records are linked
  from there. It is omitted here because this record is `Proposed` and
  because #185's own scope excludes editing the ratified file.
- **A named interface requirement is levied on the block-level top** (see
  question 3): an external 10-bit-character input per lane with a select
  against `rtl/tmds_encoder.v`'s output. It is contingent on this record being
  accepted and is tracked separately; no work on it is authorized by this
  record.
- **This record does not create the wrapper block.** Where the packet and
  character layers are implemented — inside the dongle's own digital block, or
  as a separate canary repository — is the consumer's call, not this
  repository's. This record only establishes that they are not implemented
  here.
- **The existing analog evidence is not invalidated by island characters
  passing through, and no re-characterization is implied.** The driver's
  combined swing+jitter eye result (`measurements/characterization.md`,
  DR-0013 row 6; `sim/cml-driver-eye-mask/records/20260825-040412-4b0c9f6.md`)
  is driven by a genuine PRBS7 pattern (ITU-T O.150, period 127) rather than
  by DVI-coded traffic, so it is code-agnostic by construction. What this
  record does **not** claim is a worst-case-pattern result for any particular
  code set, DVI or TERC4 — none is established here, in either direction, and
  any such claim would need its own testbench.
- **This record re-opens** if (a) a real integration shows the character-cut
  interface cannot carry data-island timing, or (b) a product decision moves
  the packet or character layer into this repository's own deliverable. Either
  would be grounds for a successor record adopting Option B with evidence.

## Status

**Proposed.** Awaiting the same human/Champion ratification every other
decision record in this repository goes through; no part of it takes effect
until then.

**Cross-references**:
[`2AMLogic/product#16`](https://github.com/2AMLogic/product/issues/16) (the
audio-in decision this record responds to) and
[`gf180-tmds-tx#185`](https://github.com/2AMLogic/gf180-tmds-tx/issues/185)
(the framing re-check that produced it).
