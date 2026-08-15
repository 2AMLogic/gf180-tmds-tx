"""Process / voltage / temperature (and, for a transient bench, bit-rate)
corner definitions for gf180mcu.

Ported from `2AMLogic/gf180-bandgap` (sim/harness/corners.py). That harness is
single-supply (a bandgap has one rail), which matches this repo's own
DR-0002/DR-0003: the driver's output devices and the synthesized digital
domain both run off gf180mcu's 3.3 V core devices, on the same rail, so no
two-rail adaptation (the one `2AMLogic/gf180-gate-driver` needed) applies
here -- ``PvtPoint`` keeps the source harness's single ``vdd`` field
unchanged.

## Process corners (unchanged from gf180-bandgap)

The gf180mcu ngspice model library (``sm141064.ngspice``) does not ship a
single "ss" switch that skews every device. Each device family carries its
own ``.lib`` section:

    MOS      typical | ff | ss | fs | sf
    BJT      bjt_typical | bjt_ff | bjt_ss
    diode    diode_typical | diode_ff | diode_ss
    resistor res_typical | res_ff | res_ss
    MOS cap  moscap_typical | moscap_ff | moscap_ss
    MIM cap  mimcap_typical | mimcap_ff | mimcap_ss

A *named corner* here is therefore a bundle of sections. Section ordering
follows the PDK's own xschem testbenches (MOS first, then passives), and
``design.ngspice`` is always included ahead of them because it defines the
global switch params (``sw_stat_global``, ``mc_skew``, ...) the sections
reference.

## The bit-rate axis (this repo's adaptation)

gf180-bandgap and gf180-gate-driver are both DC/quasi-static designs with no
rate axis. This block's claims are high-speed *transient* claims against two
distinct operating points ratified in ``spec/tmds-tx.md`` §1 -- 742.5 Mbps/
lane (720p60 target) and 270 Mbps/lane (480p fallback) -- and a result taken
at one is not evidence for the other. ``sim/README.md`` documents the
decision this module implements: the bit rate is a **first-class grid axis**,
cross-producted with process x temperature x supply exactly like any other
axis (see ``build_grid``), and its value is carried in ``PvtPoint.rate_mbps``
and rendered as a trailing ``<rate>mbps`` token in ``corner_id`` -- see
``PvtPoint.corner_id`` and ``sim/harness/evidence_lint.py``'s corner-id
grammar. A testbench with no transient rate to sweep (a DC/op-point bench,
same as every gf180-bandgap/gf180-gate-driver testbench) simply declares no
rates and ``PvtPoint.rate_mbps`` is ``None`` for every point -- the corner-id
grammar is unchanged from the source harness in that case.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

# Default PVT axes. CLAUDE.md mandates these on every recorded result.
DEFAULT_TEMPERATURES_C: tuple[float, ...] = (-40.0, 27.0, 125.0)
DEFAULT_SUPPLY_TOLERANCE: float = 0.10  # +/-10 %
DEFAULT_NOMINAL_SUPPLY_V: float = 3.3   # gf180mcu 3.3 V flavor -- DR-0002/DR-0003

#: The two ratified operating points (spec/tmds-tx.md §1). Not a "default" in
#: the PVT-axis sense -- a testbench opts into the rate axis explicitly via
#: its manifest's ``rates_mbps`` (sim/harness/testbench.py); these are just
#: the two named values sim/README.md's grammar and lint recognize as the
#: target/fallback spec rows.
RATE_TARGET_MBPS = 742.5   # 720p60 target (10:1 TMDS of 74.25 MHz pixel clock)
RATE_FALLBACK_MBPS = 270.0  # 480p fallback (10:1 TMDS of 27.000 MHz pixel clock)

#: The corner-id grammar's literal supply token for a testbench with no
#: supply rail to sweep -- see ``sim/README.md`` and ``PvtPoint.corner_id``.
NO_SUPPLY = "nosupply"


def _bundle(mos: str, bjt: str, diode: str, res: str, moscap: str, mimcap: str) -> tuple[str, ...]:
    return (mos, res, bjt, diode, moscap, mimcap)


@dataclass(frozen=True)
class Corner:
    """A named process corner: an ordered list of model ``.lib`` sections."""

    name: str
    sections: tuple[str, ...]
    description: str = ""


def _all(skew: str, description: str) -> Corner:
    """Global corner: every device family skewed the same direction."""
    suffix = {"ff": "ff", "ss": "ss"}[skew]
    return Corner(
        name=skew,
        sections=_bundle(
            mos=suffix,
            bjt=f"bjt_{suffix}",
            diode=f"diode_{suffix}",
            res=f"res_{suffix}",
            moscap=f"moscap_{suffix}",
            mimcap=f"mimcap_{suffix}",
        ),
        description=description,
    )


_TYPICAL = _bundle(
    mos="typical",
    bjt="bjt_typical",
    diode="diode_typical",
    res="res_typical",
    moscap="moscap_typical",
    mimcap="mimcap_typical",
)


def _mos_only(name: str, mos_section: str, description: str) -> Corner:
    """MOS skewed, passives at typical."""
    sections = (mos_section,) + _TYPICAL[1:]
    return Corner(name=name, sections=sections, description=description)


def _passive_only(name: str, family_index: int, section: str, description: str) -> Corner:
    sections = list(_TYPICAL)
    sections[family_index] = section
    return Corner(name=name, sections=tuple(sections), description=description)


CORNERS: dict[str, Corner] = {
    "tt": Corner("tt", _TYPICAL, "all device families typical"),
    "ff": _all("ff", "all device families fast"),
    "ss": _all("ss", "all device families slow"),
    "fs": _mos_only("fs", "fs", "fast NMOS / slow PMOS, passives typical"),
    "sf": _mos_only("sf", "sf", "slow NMOS / fast PMOS, passives typical"),
    # Passive-dominated corners: the CML driver's output impedance (the 50 ohm
    # per-leg termination target, DR-0002) rides on resistor sheet rho.
    "res_ff": _passive_only("res_ff", 1, "res_ff", "resistors fast (low rho), rest typical"),
    "res_ss": _passive_only("res_ss", 1, "res_ss", "resistors slow (high rho), rest typical"),
    "bjt_ff": _passive_only("bjt_ff", 2, "bjt_ff", "BJTs fast, rest typical"),
    "bjt_ss": _passive_only("bjt_ss", 2, "bjt_ss", "BJTs slow, rest typical"),
}

CORNER_SETS: dict[str, tuple[str, ...]] = {
    # Minimum bar for a quick smoke run.
    "tt": ("tt",),
    # The five classic MOS corners -- the default.
    "mos": ("tt", "ff", "ss", "fs", "sf"),
    # Everything: MOS corners plus resistor / BJT skews.
    "full": ("tt", "ff", "ss", "fs", "sf", "res_ff", "res_ss", "bjt_ff", "bjt_ss"),
}
DEFAULT_CORNER_SET = "mos"


def resolve_corners(names: list[str] | tuple[str, ...] | None) -> list[Corner]:
    """Turn a list of corner *or* corner-set names into Corner objects."""
    if not names:
        names = [DEFAULT_CORNER_SET]
    resolved: list[Corner] = []
    seen: set[str] = set()
    for name in names:
        expanded = CORNER_SETS.get(name, (name,))
        for corner_name in expanded:
            if corner_name in seen:
                continue
            if corner_name not in CORNERS:
                raise KeyError(
                    f"unknown corner {corner_name!r}; "
                    f"known corners: {', '.join(sorted(CORNERS))}; "
                    f"known sets: {', '.join(sorted(CORNER_SETS))}"
                )
            seen.add(corner_name)
            resolved.append(CORNERS[corner_name])
    return resolved


def supply_points(
    nominal_v: float = DEFAULT_NOMINAL_SUPPLY_V,
    tolerance: float = DEFAULT_SUPPLY_TOLERANCE,
) -> list[float]:
    """Nominal supply and its +/- tolerance rails, low to high."""
    if tolerance <= 0:
        return [round(nominal_v, 6)]
    return [
        round(nominal_v * (1.0 - tolerance), 6),
        round(nominal_v, 6),
        round(nominal_v * (1.0 + tolerance), 6),
    ]


def _format_rate_token(rate_mbps: float) -> str:
    """``742.5`` -> ``742p5mbps``, ``270.0`` -> ``270mbps``.

    ``p`` stands in for the decimal point (same convention
    ``PvtPoint.corner_id``'s ``<supply>`` field already uses) so the whole
    ``<rate>`` field stays a single underscore-free token; ``%g`` drops a
    trailing ``.0`` so the common integer-Mbps case (``270``) reads plainly.
    """
    return f"{rate_mbps:g}".replace(".", "p") + "mbps"


@dataclass(frozen=True)
class PvtPoint:
    """One point in the PVT (or PVT x rate) grid -- exactly one ngspice
    invocation."""

    corner: Corner
    temp_c: float
    vdd: float
    rate_mbps: float | None = None

    @property
    def corner_id(self) -> str:
        """The ``<process>_<temp>c_<supply>v[_<rate>mbps]`` id from
        ``sim/README.md``.

        This is the ratified corner naming for evidence records: the raw log
        for this point is ``corners/<record-id>/<corner-id>.log`` (e.g.
        ``ss_-40c_2.97v.log`` for a DC/op-point bench,
        ``tt_27c_3.30v_742p5mbps.log`` for a transient bench swept over the
        rate axis). The trailing ``<rate>`` field is present only when
        ``rate_mbps`` is set -- omitting it for every non-transient testbench
        keeps this identical to the un-adapted gf180-bandgap grammar.
        """
        base = f"{self.corner.name}_{self.temp_c:g}c_{self.vdd:.2f}v"
        if self.rate_mbps is None:
            return base
        return f"{base}_{_format_rate_token(self.rate_mbps)}"

    def as_dict(self) -> dict:
        record = {
            "corner": self.corner.name,
            "corner_sections": list(self.corner.sections),
            "temp_c": self.temp_c,
            "vdd": self.vdd,
            "corner_id": self.corner_id,
        }
        if self.rate_mbps is not None:
            record["rate_mbps"] = self.rate_mbps
        return record


def build_grid(
    corners: list[Corner],
    temperatures: list[float] | tuple[float, ...],
    supplies: list[float],
    rates_mbps: list[float] | tuple[float, ...] | None = None,
) -> list[PvtPoint]:
    """Full factorial P x V x T (x rate, when given) grid, in a stable,
    reproducible order.

    ``rates_mbps`` is ``None`` (not an empty list) for a testbench with no
    rate axis -- every :class:`PvtPoint` then carries ``rate_mbps=None`` and
    ``corner_id`` renders exactly as the un-adapted source harness would.
    Passing ``rates_mbps=()`` is rejected rather than silently producing zero
    points, since that is almost always a caller bug (an empty override list)
    rather than an intentional "no rate axis".
    """
    if rates_mbps is not None and len(rates_mbps) == 0:
        raise ValueError(
            "rates_mbps must be None (no rate axis) or a non-empty sequence, not []"
        )
    rate_values: list[float | None] = list(rates_mbps) if rates_mbps is not None else [None]
    points = [
        PvtPoint(
            corner=corner,
            temp_c=float(temp),
            vdd=float(vdd),
            rate_mbps=(None if rate is None else float(rate)),
        )
        for corner, temp, vdd, rate in itertools.product(
            corners, temperatures, supplies, rate_values
        )
    ]
    return points
