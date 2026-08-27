# tmds-tx comp data (generated, public-sources-only)

Generated 2026-08-27 from the upstream comp library's `tmds-tx.md` entry by an internal, private-repo-only tool. This is a derived, filtered copy — regenerate rather than hand-edit. Every row below cites a public vendor datasheet or a public distributor pricing page; nothing internal survived extraction.

## Comparable parts

| Vendor | Part | Class | Max rate/lane | Output swing | HDCP / audio / CEC | Package | Price | Source |
|---|---|---|---|---|---|---|---|---|
| Texas Instruments | TFP410 | DVI 1.0-compliant transmitter (PanelBus), no HDCP/audio | 1.65 Gbps (165 MHz pixel clock, well above our 742.5 Mbps target) | 400–600 mVP-P (RTFADJ = 510 Ω ± 1%, into 50 Ω ± 10% at 3.3 V ± 5% AVDD) — matches our 400–600 mV working-range target almost exactly | None (DVI 1.0 only; no HDCP, no audio, no CEC) | 64-pin TQFP (PowerPAD), 12×12 mm | $8.516 (1-99), $4.628 (1000+) — TFP410PAP, TI direct pricing | Datasheet: [ti.com/lit/ds/symlink/tfp410.pdf](https://www.ti.com/lit/ds/symlink/tfp410.pdf) (SLDS145D, rev. Feb 2024). Pricing: [ti.com/product/TFP410](https://www.ti.com/product/TFP410) |
| Analog Devices | ADV7511 | 225 MHz HDMI 1.4 transmitter with HDCP 1.4, ARC, CEC, 8-channel I2S/S-PDIF audio; DVI 1.0-compatible mode also supported | 2.25 Gbps (225 MHz pixel clock, incl. 12-bit Deep Color) — no TMDS electrical (swing/jitter) figures in the 2-page product brief fetched | not stated in the fetched brief | HDCP 1.4, 8-ch I2S + S/PDIF audio up to 192 kHz (768 kHz via I2S), CEC + ARC (HEAC) | 100-lead LQFP | not fetched (analog.com unreachable live; no distributor pricing checked) | Datasheet (product brief, Rev. Sp0, ©2010): canonical URL [analog.com/media/en/technical-documentation/data-sheets/ADV7511.pdf](https://www.analog.com/media/en/technical-documentation/data-sheets/ADV7511.pdf), fetched via Wayback Machine snapshot [web.archive.org/web/20240427201952/.../ADV7511.pdf](http://web.archive.org/web/20240427201952/http://www.analog.com/media/en/technical-documentation/data-sheets/ADV7511.pdf) |

## Sources

| URL | Establishes | Fetched |
|---|---|---|
| https://www.ti.com/lit/ds/symlink/tfp410.pdf | TFP410 rate, swing, ESD, package, supply (SLDS145D) | 2026-08-24 |
| https://www.ti.com/product/TFP410 | TFP410PAP / TFP410PAPR TI-direct pricing | 2026-08-24 |

