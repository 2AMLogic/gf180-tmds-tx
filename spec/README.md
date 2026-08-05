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

A decision record's `Status` is one of: `Proposed`, `Accepted`,
`Accepted — provisional` (accepted but conditional on a stated follow-up,
e.g. another issue's findings), or `Superseded by DR-NNNN` (never delete a
decision record; supersede it and say why).
