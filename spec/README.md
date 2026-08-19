# spec

The ratified target specification lives in [`tmds-tx.md`](tmds-tx.md): the
parameter table engineering designs to, the numeric PLL interface contract
(reference frequency, output frequencies, jitter budget), and the pad-cell /
ESD strategy.

## Decision-record convention

Spec changes go through this directory with a decision record — CLAUDE.md
requires it, and `tmds-tx.md` is the first document to follow it. The
convention: a lightweight ADR-style entry per decision — **Context, Decision,
Alternatives Considered, Consequences, Status** — identified as `DR-NNNN`
(zero-padded, monotonically increasing across the whole spec, not per file).

Decision records live inline in `tmds-tx.md` under its "Decision records"
section for now. If the number of decisions grows large enough that inline
entries become unwieldy, split them into individual `spec/decisions/NNNN-*.md`
files and link them from `tmds-tx.md` instead — but do not restructure
preemptively; inline is the default until it isn't.

**The split clause fired at DR-0010** (issue #9): `tmds-tx.md` had grown to
nine inline decision records (DR-0001–DR-0009) by the time four more landed
at once, and the four new records were larger than the file's own inline
average. DR-0001–DR-0009 stay inline (relocating already-ratified prose is
its own unnecessary churn, not required by this convention); **DR-0010
onward live in `spec/decisions/NNNN-*.md`**, linked from `tmds-tx.md`'s
"Further decision records (index)" subsection at the end of its "Decision
records" section. A future split point, if the inline set grows again, is
whichever record makes inline entries unwieldy at that time — not a
retroactive migration of everything already inline.

**Numbering stays monotonic across both forms.** A record's number is
assigned when it is drafted, regardless of whether it ends up inline or in
its own file — issue #9's own decision records were originally drafted as
`DR-0006`–`DR-0009` before four *other*, unrelated records claimed those
exact numbers first (ratified while #9 was still open); the drafts were
renumbered to `DR-0010`–`DR-0013` rather than force a collision. See
`spec/decisions/0010-pdk-variant.md`'s "Renumbering note" for the full
account. **Before drafting a new decision record, check the highest number
already in use across *both* `tmds-tx.md`'s inline set and
`spec/decisions/`** — not just one or the other — to avoid the same
collision recurring.

A decision record's `Status` is one of: `Proposed`, `Accepted`,
`Accepted — provisional` (accepted but conditional on a stated follow-up,
e.g. another issue's findings), or `Superseded by DR-NNNN` (never delete a
decision record; supersede it and say why).
