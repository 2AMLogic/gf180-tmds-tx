"""Shared fixture scaffolding for the ``sim/tests`` harness suites.

The loader/builder primitives every suite was carrying as a private copy
live here so a fix lands once -- the same call ``_dut_netlist.py`` already
made for the extracted-DUT suites. ``unittest discover``'s ``test*.py``
pattern ignores this module, so it is never collected as a test of its own.

Per-caller state stays isolated by construction: ``load_run_mc`` registers
each caller's module under its own ``sys.modules`` alias (a caller like
``test_evidence_store.py`` monkeypatches module globals and must not share
state with a sibling suite's copy), and the temporary-directory helpers
register cleanup on the calling case's own ``addCleanup``.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

from harness import batch as batch_mod  # noqa: E402
from harness import corners as corners_mod  # noqa: E402
from harness import runner as runner_mod  # noqa: E402
from harness import testbench as tb_mod  # noqa: E402
from harness.pdk import Pdk  # noqa: E402

RUN_MC_PATH = SIM_DIR / "cml-driver-mismatch" / "run_mc.py"


def load_testbench(
    case: unittest.TestCase, manifest: dict, netlist_body: str = "* fragment\n"
) -> tb_mod.Testbench:
    """Write ``manifest`` and its netlist fragment into a fresh temporary
    directory, register that directory's removal with the calling test's
    ``addCleanup``, and load a Testbench with the real loader (issue #394).

    The directory outlives the call: unlike a Testbench returned from inside
    a ``TemporaryDirectory`` context manager -- whose files are deleted
    before any assertion runs -- the loaded Testbench's netlist file and its
    ``netlist_sha256``/``manifest_sha256`` stay readable until the calling
    test's own cleanup. Tests needing two fixtures in one method simply call
    this twice; each call gets its own directory.
    """
    tmp = tempfile.mkdtemp()
    case.addCleanup(shutil.rmtree, tmp, True)
    directory = Path(tmp) / "exp" / "testbench"
    directory.mkdir(parents=True)
    (directory / "frag.spice").write_text(netlist_body)
    (directory / tb_mod.MANIFEST_NAME).write_text(json.dumps(manifest))
    return tb_mod.load(directory)


def fake_pdk() -> Pdk:
    """The text-only-composition PDK stand-in.

    A nonexistent path is fine: ``compose_deck``/``compose_body`` only ever
    render ``pdk.variant``/``pdk.version``/``pdk.design_include``/
    ``pdk.model_lib`` into deck text, and the batch request builders only
    relativize ``model_lib`` against ``path`` -- none of them reads these
    files, and ``version`` falls back to ``"unknown"`` with no ``SOURCES``
    file present.
    """
    return Pdk(path=Path("/nonexistent/gf180mcuD"), variant="gf180mcuD", source="test")


def make_point(
    corner: str = "tt",
    temp_c: float = 27.0,
    vdd: float = 3.3,
    rate_mbps: float | None = None,
) -> corners_mod.PvtPoint:
    return corners_mod.PvtPoint(
        corner=corners_mod.CORNERS[corner], temp_c=temp_c, vdd=vdd, rate_mbps=rate_mbps
    )


def load_run_mc(alias: str):
    """Load ``sim/cml-driver-mismatch/run_mc.py`` as a module object.

    The directory name contains a hyphen, so Python cannot import it by
    dotted path, and ``@dataclass`` processing resolves annotations through
    ``sys.modules`` -- the module must be registered there before
    ``exec_module``. Each caller passes its own ``alias`` so two test
    modules never share module state. Loading runs only imports and
    constant definitions -- no PDK discovery, ngspice probe or sweep.
    """
    spec = importlib.util.spec_from_file_location(alias, RUN_MC_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def init_git_repo(
    case: unittest.TestCase,
) -> tuple[Path, Callable[..., subprocess.CompletedProcess]]:
    """A throwaway git repo: temp directory with cleanup on ``case``, ``git
    init`` and committer identity configured.

    Returns ``(root, git_fn)`` where ``git_fn`` runs ``git`` inside ``root``
    (checked, text mode). Seeding the tree and committing is the caller's
    job -- each suite commits a different shape of fixture.
    """
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    root = Path(tmp.name)

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ("git", *args),
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

    git("init", "--quiet")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "test")
    return root, git


def options_testbench(case: unittest.TestCase, **extra) -> tb_mod.Testbench:
    """The minimal op-point manifest the ``.options`` suites feed both
    composers, plus whatever ``options``/``transient`` the test adds."""
    manifest = {
        "netlist": "frag.spice",
        "measure": {"vout": "v(out)"},
        "analyses": ["op"],
    }
    manifest.update(extra)
    return load_testbench(case, manifest)


def both_options_lines(
    case: unittest.TestCase, **extra
) -> tuple[list[str], list[str]]:
    """The ``.options`` lines each backend renders for the same testbench."""
    tb = options_testbench(case, **extra)
    pdk, point = fake_pdk(), make_point()
    deck = runner_mod.compose_deck(tb, pdk, point)
    body = batch_mod.compose_body(tb, pdk, point)
    return (
        [ln.strip() for ln in deck.splitlines() if ln.strip().startswith(".options")],
        [ln.strip() for ln in body.splitlines() if ln.strip().startswith(".options")],
    )
