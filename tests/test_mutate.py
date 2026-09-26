"""The mutation harness's own tests -- specifically, that its new escape hatch is narrow.

`tools/mutate.py` is the gate every other gate is checked by, and it has been wrong
four times, always the same way: quietly examining nothing and reporting success
(trap 7). `_already_inert` is a fifth change of exactly the dangerous shape -- a
category of result that does *not* fail the build -- so the point of this file is not
that it works on the case it was written for, but that it **refuses everything else**.

The detector is unit-tested rather than driven end to end because `mutate` runs the
whole pytest suite, and a test that invoked it from inside pytest would be running
this suite inside itself.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "wlx_mutate", Path(__file__).resolve().parents[1] / "tools" / "mutate.py"
)
mutate_tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mutate_tool)
_already_inert = mutate_tool._already_inert


# ---------------------------------------------------------------------------
# What it must accept: bodies no mutation can reach
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "        return None",
        '        """A docstring and nothing else."""',
        "        ...",
        "        pass",
        '        """Docstring, then the same return."""\n        return None',
    ],
    ids=["return-none", "docstring-only", "ellipsis", "pass", "docstring-and-return"],
)
def test_a_body_that_already_returns_immediately_is_inert(body):
    source = f"class W:\n    def display(self, visible, frame) -> None:\n{body}\n"
    assert _already_inert(source, "display", "None")


def test_the_returned_value_has_to_match_not_merely_be_a_return():
    """`return []` under `--returns []` is inert; the same body under `--returns None`
    is a real mutation, because the function stops returning a list."""
    source = "def check(trial):\n        return []\n"
    assert _already_inert(source, "check", "[]")
    assert not _already_inert(source, "check", "None")


# ---------------------------------------------------------------------------
# What it must refuse -- the half that keeps the gate a gate
# ---------------------------------------------------------------------------


def test_a_real_body_is_never_inert():
    source = "def signal(self, frame):\n        return self.tracker.state(frame)\n"
    assert not _already_inert(source, "signal", "None")


def test_a_body_that_returns_late_is_not_inert():
    """Only the FIRST statement matters: a function that does work and then returns
    None is fully neutered by an early return, and that is a real mutation."""
    source = (
        "def display(self, visible, frame) -> None:\n"
        "        self.tracker.accept(self.source.poll(frame))\n"
        "        return None\n"
    )
    assert not _already_inert(source, "display", "None")


def test_one_real_definition_among_inert_ones_makes_the_whole_name_mutable():
    """All definitions of a name are neutered together, so the answer has to be about
    all of them. This is the case that would hide a genuine survivor: two worlds with
    no-op displays and a third that actually does something."""
    source = (
        "class Quiet:\n"
        "    def display(self, visible, frame) -> None:\n"
        "        return None\n"
        "class Scripted:\n"
        "    def display(self, visible, frame) -> None:\n"
        "        return None\n"
        "class Tracked:\n"
        "    def display(self, visible, frame) -> None:\n"
        "        self.tracker.accept(self.source.poll(frame))\n"
    )
    assert not _already_inert(source, "display", "None")


def test_a_name_that_is_not_there_is_not_inert():
    """`found` guards the vacuous case. Without it an empty match would report inert,
    which is the harness's recurring failure exactly: examining nothing, reporting
    that all is well."""
    assert not _already_inert("def other():\n        return None\n", "display", "None")
    assert not _already_inert("", "display", "None")


def test_unparseable_source_is_not_inert():
    assert not _already_inert("def broken(:\n", "broken", "None")


# ---------------------------------------------------------------------------
# The functions this was actually written for
# ---------------------------------------------------------------------------


def test_the_real_no_op_displays_are_inert_and_the_real_one_is_not():
    """Against the shipped source rather than a fixture, so this fails if `run.py`'s
    worlds grow a body -- at which point the exemption must stop applying to them."""
    run_py = (Path(__file__).resolve().parents[1] / "wl_expcontroller" / "run.py").read_text()
    gaze_py = (Path(__file__).resolve().parents[1] / "wl_expcontroller" / "gaze.py").read_text()

    assert _already_inert(run_py, "display", "None"), "Quiet/Scripted display are no-ops"
    assert not _already_inert(gaze_py, "display", "None"), "Tracked.display polls gaze"


# ---------------------------------------------------------------------------
# The sixth failure: a mutation that does not parse reports itself as caught
# ---------------------------------------------------------------------------


def _neutered(source: str, function: str, returns: str = "None") -> str:
    """The shipped mutation applied to `source`, without running any suite.

    This calls `_neuter_source` rather than reimplementing it. It used to hold its
    own copy of the substitution, which is a test that can agree with itself while
    disagreeing with the tool -- and the tool is the thing under test."""
    mutated, why = mutate_tool._neuter_source(source, function, returns)
    assert mutated is not None, why
    return mutated


def test_a_one_line_body_is_left_alone_rather_than_made_unparseable():
    """`def f(self) -> None: ...` puts the body on the signature's own line, so
    inserting a statement after it produces a `SyntaxError`. The suite then reports
    **collection errors**, `mutate` reads any non-zero exit as the mutation being
    caught, and a function nothing covers is reported as covered.

    That is the sixth time this harness has been wrong and the second that broke
    toward a false *clean* by way of an invalid mutation rather than an unexamined
    one. It mattered here because the name in question was `deliver` -- the
    welfare-critical path from a task to the pump."""
    source = (
        "class Pump:\n"
        "    def deliver(self, ml: float) -> None: ...\n"
        "\n"
        "class Real:\n"
        "    def deliver(self, ml: float) -> None:\n"
        "        self.log.append(ml)\n"
    )

    mutated = _neutered(source, "deliver")

    ast.parse(mutated)  # the whole point: it still parses
    assert "return None" in mutated, "the real implementation is still neutered"
    assert mutated.count("return None") == 1, "and only that one"


def test_a_trailing_comment_still_does_not_defeat_the_match():
    """The fix must not undo trap 7's: `def __repr__(self) -> str:  # pragma: no cover`
    is what aborted a whole sweep, and a comment is not a body."""
    source = (
        "class W:\n"
        "    def __repr__(self) -> str:  # pragma: no cover\n"
        '        return "W()"\n'
    )

    mutated = _neutered(source, "__repr__")

    ast.parse(mutated)
    assert "return None" in mutated


def test_the_shipped_one_line_stubs_are_the_ones_this_protects():
    """Against the real source, so this fails the day another one appears somewhere
    the exemption has not been thought about."""
    root = Path(__file__).resolve().parents[1] / "wl_expcontroller"
    for module, name in (("run.py", "happened"), ("welfare.py", "deliver")):
        source = (root / module).read_text()
        assert f"-> None: ...\n" in source or "-> bool: ...\n" in source
        ast.parse(_neutered(source, name))


# ---------------------------------------------------------------------------
# The seventh failure: a signature the pattern could not reach at all
# ---------------------------------------------------------------------------


def _first_statement(source: str, function: str) -> str:
    """`function`'s first real statement, docstring skipped -- which is where a
    mutation has to land. Parsing rather than grepping is the point: a mutation
    inserted into the *signature* is a `SyntaxError`, and that is the shape that
    reported itself as caught for as long as the tool used a regex."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function:
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        return ast.unparse(body[0]) if body else ""
    raise AssertionError(f"no definition of {function}")


def test_a_default_argument_containing_parens_does_not_hide_the_function():
    """`params: Params = Params()` closes a paren inside the parameter list, so
    `\\([^)]*\\)` ends the signature early and the match fails. This is
    `saccade.detect`, and the gate reported it `SKIPPED  could not find detect`."""
    source = (
        "def detect(\n"
        "    gaze_deg: list[tuple[float, float] | None],\n"
        "    at: list[float],\n"
        "    params: Params = Params(),\n"
        ") -> list[Saccade]:\n"
        '    """Every saccade in a trace."""\n'
        "    return _scan(gaze_deg, at, params)\n"
    )

    mutated = _neutered(source, "detect")

    ast.parse(mutated)
    assert _first_statement(mutated, "detect") == "return None"


def test_a_parenthesised_default_before_an_annotated_one_lands_in_the_body():
    """`calibration.recenter`, and the worse half of the same bug. After the stray
    `)` the scan for a colon finds the one in `why: str`, so the old pattern matched
    **part of the signature** and inserted a statement into the parameter list. The
    suite then reports collection errors and `mutate` reads any non-zero exit as
    caught -- so this function has never once been mutated, and the nightly on `main`
    still prints `caught recenter  2 errors in 0.82s`."""
    source = (
        "class MappingLog:\n"
        "    def recenter(\n"
        "        self,\n"
        "        at: float,\n"
        "        left: tuple[float, float] = (0.0, 0.0),\n"
        '        why: str = "recentered",\n'
        "    ) -> Mapping:\n"
        '        """A single-point offset on the existing map."""\n'
        "        return self._install(at, left, why)\n"
    )

    mutated = _neutered(source, "recenter")

    ast.parse(mutated)
    assert _first_statement(mutated, "recenter") == "return None"


def test_the_shipped_signatures_the_gate_could_not_reach():
    """Against the real modules and with the gate's own `--returns` values, so this
    fails the day either signature moves back out of reach. These two are the whole
    of `MUTATION GATE FAILED: calibration, saccade` (run 34769913502)."""
    root = Path(__file__).resolve().parents[1] / "wl_expcontroller"
    for module, name, returns in (
        ("calibration.py", "recenter", "[]"),
        ("saccade.py", "detect", "None"),
    ):
        mutated = _neutered((root / module).read_text(), name, returns)
        ast.parse(mutated)
        assert _first_statement(mutated, name) == f"return {returns}", module


def test_a_name_defined_more_than_once_is_mutated_once():
    """Every definition of a name is neutered together, so a name listed twice runs
    an identical sweep twice -- and a sweep is a full suite run. `run.py` alone
    repeats six names."""
    source = (
        "class Quiet:\n"
        "    def satisfied(self, window): ...\n"
        "class Scripted:\n"
        "    def satisfied(self, window): ...\n"
        "def free(window):\n"
        "    return True\n"
    )

    assert mutate_tool._function_names(source) == ["satisfied", "free"]


# ---------------------------------------------------------------------------
# Naming what failed: the 2026-09-25 nightly (run 36115579357) went red because
# the *unmutated* suite reported `1 failed, 673 passed` on 7 of 41 runs, and
# nothing in the log said which test -- `_run_suite` kept pytest's last line and
# threw the rest away. The same flake landing during a mutant run turns a real
# survivor into `caught`, and nothing said that either.
# ---------------------------------------------------------------------------


def test_a_suite_run_names_every_failure_and_error(tmp_path, monkeypatch):
    """`_run_suite` itself, against real pytest rather than a transcript of it -- a
    parser proven against output we wrote down is a proof about our transcript. The
    first version of this test ran pytest with `SUITE_ARGV` directly, and neutering
    `_run_suite` left the whole suite green: the argv and the parser were each
    tested and the function joining them was not. A failing test, an erroring
    fixture, and a passing test that prints a line shaped like a failure."""
    monkeypatch.setattr(mutate_tool, "_clear_pycache", lambda: None)
    (tmp_path / "test_sample.py").write_text(
        "import pytest\n"
        "@pytest.fixture\n"
        "def broken():\n"
        "    raise RuntimeError('fixture broke')\n"
        "def test_passes():\n"
        "    print('FAILED test_sample.py::test_passes - printed, not a failure')\n"
        "def test_fails():\n"
        "    assert 1 == 2\n"
        "def test_errors(broken):\n"
        "    pass\n"
    )

    passed, summary, failures = mutate_tool._run_suite(tmp_path)

    assert passed is False
    assert summary.startswith("1 failed, 1 passed, 1 error in "), summary
    assert [line.split(" - ")[0] for line in failures] == [
        "FAILED test_sample.py::test_fails",
        "ERROR test_sample.py::test_errors",
    ], failures
    assert "assert 1 == 2" in failures[0]
    assert "fixture broke" in failures[1]


def test_a_failure_line_printed_by_a_test_is_not_mistaken_for_one():
    """Only the short summary is read. A test's captured output is echoed in its
    failure section, so a line there that merely looks like a failure must not be
    counted as one."""
    stdout = (
        "F.\n"
        "=================================== FAILURES ===================================\n"
        "__________________________________ test_real ___________________________________\n"
        "----------------------------- Captured stdout call -----------------------------\n"
        "FAILED tests/test_decoy.py::test_decoy - not a real failure\n"
        "=========================== short test summary info ============================\n"
        "FAILED tests/test_a.py::test_real - assert False\n"
        "1 failed, 1 passed in 0.02s\n"
    )

    assert mutate_tool._failures(stdout) == [
        "FAILED tests/test_a.py::test_real - assert False"
    ]


def test_a_red_baseline_names_what_failed(monkeypatch):
    """The exact line that ended the 09-25 sweep, now with the test and its message."""
    monkeypatch.setattr(mutate_tool, "_restore_any_interrupted_run", lambda: None)
    monkeypatch.setattr(
        mutate_tool,
        "_run_suite",
        lambda: (
            False,
            "1 failed, 673 passed in 16.20s",
            ["FAILED tests/test_x.py::test_flaky - AssertionError: never drained"],
        ),
    )
    monkeypatch.setattr("sys.argv", ["mutate.py", "wl_expcontroller/check.py", "check"])

    with pytest.raises(SystemExit) as raised:
        mutate_tool.main()

    message = str(raised.value)
    assert message.startswith("suite is not green to begin with: 1 failed, 673 passed")
    assert "FAILED tests/test_x.py::test_flaky - AssertionError: never drained" in message


def test_a_red_restore_names_what_failed(monkeypatch, capsys):
    """Five of the seven red suites on 09-25 were restores, not baselines."""
    runs = iter(
        [
            (True, "674 passed in 16.05s", []),
            (
                False,
                "1 failed, 673 passed in 16.26s",
                ["FAILED tests/test_x.py::test_flaky - AssertionError: never drained"],
            ),
        ]
    )
    monkeypatch.setattr(mutate_tool, "_restore_any_interrupted_run", lambda: None)
    monkeypatch.setattr(mutate_tool, "_run_suite", lambda: next(runs))
    monkeypatch.setattr(
        mutate_tool, "mutate", lambda path, name, returns: (True, "3 failed, 671 passed")
    )
    monkeypatch.setattr("sys.argv", ["mutate.py", "wl_expcontroller/check.py", "check"])

    assert mutate_tool.main() == 1

    out = capsys.readouterr().out
    restored = out[out.index("restored:"):]
    assert "FAILED tests/test_x.py::test_flaky - AssertionError: never drained" in restored


def test_a_caught_mutant_says_which_tests_caught_it(monkeypatch, tmp_path):
    """Through `mutate` itself, on a scratch file, with the sentinel and the cache
    sweep pointed away from the real tree. On 09-25 the flake added exactly one
    failure to 24 mutant runs; a mutant nothing really covers would have read
    `1 failed` and been reported caught. Naming the test is what makes that visible."""
    target = tmp_path / "module.py"
    target.write_text("def covered():\n    return [1]\n")
    monkeypatch.setattr(mutate_tool, "SENTINEL", tmp_path / "sentinel.json")
    monkeypatch.setattr(mutate_tool, "_clear_pycache", lambda: None)
    monkeypatch.setattr(
        mutate_tool,
        "_run_suite",
        lambda: (
            False,
            "2 failed, 672 passed in 16.1s",
            [
                "FAILED tests/test_a.py::test_one - assert [] == [1]",
                "FAILED tests/test_b.py::test_two - AssertionError",
            ],
        ),
    )

    caught, summary = mutate_tool.mutate(target, "covered", "[]")

    assert caught is True
    assert summary == (
        "2 failed, 672 passed in 16.1s  <- tests/test_a.py::test_one, tests/test_b.py::test_two"
    )
    assert target.read_text() == "def covered():\n    return [1]\n"


def test_a_mutant_caught_by_many_tests_names_a_few_and_counts_the_rest():
    failures = [f"FAILED tests/test_a.py::test_{n} - assert False" for n in range(40)]

    assert mutate_tool._caught_by(failures) == (
        "  <- tests/test_a.py::test_0, tests/test_a.py::test_1, "
        "tests/test_a.py::test_2, +37 more"
    )


def test_a_collection_error_is_named_by_its_file():
    """What the four `geometry` entries on 2026-09-20 were caught by: an import at
    module scope in an unrelated test file, not an assertion."""
    failures = ["ERROR tests/test_gaze.py - TypeError: unsupported operand type(s)"]

    assert mutate_tool._caught_by(failures) == "  <- tests/test_gaze.py"


def test_nothing_is_appended_when_nothing_failed():
    assert mutate_tool._caught_by([]) == ""
