# spec

Ratified specifications and decision records for this block.

| Document | Contents |
|---|---|
| [`tmds-tx.md`](tmds-tx.md) | **The ratified block specification.** Parameter tables, interfaces, budgets, signoff criteria. |
| [`decisions/`](decisions/) | Decision records (ADRs). One file per decision, numbered. |

`tmds-tx.md` is the single source of truth for the block's targets. The
README at the repo root does not restate any of these numbers — it points
here — so there is exactly one copy to keep correct.

## Decision-record convention

This repo uses lightweight ADR-style records, one file per decision:

```
spec/decisions/NNNN-short-kebab-title.md
```

`NNNN` is a zero-padded sequence number, allocated in order and never
reused. Each record has five sections, in this order:

| Section | Contents |
|---|---|
| **Status** | `Accepted` / `Superseded by NNNN` / `Proposed`, plus the date. |
| **Context** | The facts and constraints that forced a choice. Cite primary sources — PDK files with paths, extracted or simulated numbers, issue numbers. Facts that could not be verified go in **Open items** at the bottom of the record, not silently into Context. |
| **Decision** | What was chosen, stated so a reader can tell whether a later design complies with it. Numeric wherever a number exists. |
| **Alternatives considered** | Each rejected option and the specific reason it lost. An option that was never on the table does not belong here. |
| **Consequences** | What this commits the block to, including costs and anything it makes harder or impossible. Downstream issues that inherit the decision are named. |

Rules:

- **A change to a ratified number requires a new record.** Do not edit an
  accepted record to make a result pass. Write a new record that supersedes
  it, set the old record's Status to `Superseded by NNNN`, and update
  `tmds-tx.md`.
- **Records are append-only in spirit.** Fixing a typo or a broken link is
  fine; changing what was decided is not.
- **Pre-agreed contingencies are still decisions.** Where a record names a
  fallback with an objective trigger (see [`0006`](decisions/0006-pad-cell-and-esd-strategy.md)),
  invoking that fallback still requires a new record stating that the trigger
  fired and what the measurement was. The contingency exists so the fallback
  is chosen in advance rather than under schedule pressure — not so it can be
  taken silently.
- **Every claim must be traceable.** A PDK fact cites a file path; a
  simulated number cites the testbench and corner set; a number taken from an
  external standard cites the clause and, if it could not be checked against
  the document itself, says so.

## Index of decisions

| # | Title | Status |
|---|---|---|
| [0001](decisions/0001-resolution-ladder.md) | Resolution ladder, and the standing of 1080p60 | Accepted 2026-08-05 |
| [0002](decisions/0002-reference-clock-and-clock-mastership.md) | 27 MHz reference; the transmitter is clock master | Accepted 2026-08-05 |
| [0003](decisions/0003-serializer-partition.md) | Where the standard-cell / custom / CML boundaries fall | Accepted 2026-08-05 |
| [0004](decisions/0004-driver-topology-and-supplies.md) | Cascoded current-steering driver, device flavors, supply domains | Accepted 2026-08-05 |
| [0005](decisions/0005-pll-interface-and-jitter-budget.md) | PLL interface and the jitter budget levied on it | Accepted 2026-08-05 |
| [0006](decisions/0006-pad-cell-and-esd-strategy.md) | Adapt `gf180mcu_fd_io__asig_5p0`; 2 kV HBM / 500 V CDM | Accepted 2026-08-05 |
