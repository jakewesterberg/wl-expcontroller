"""The backlog keeps its shape, so it stays a list rather than becoming a diary.

`docs/backlog.md` exists because to-dos written into one day's CHECKPOINT entry sank
under the next day's, and because the per-plan ledgers that held deferred review
findings are git-ignored and deleted when a plan finishes. The failure it replaces is
narrative accreting where a list should be -- wl-works' own queues grew to thousands of
lines of items restated at length -- so what is checked here is the shape: six sections
and no others, one line per item, an ID nothing else has, an origin with a date and a
link, and something said about what it waits on. Nothing else may sit in a section.

The file maps to no module, so the mutation gate selects nothing for it; each check
below was shown to fail with the backlog deliberately broken, and the file restored
(2026-09-28).
"""

from __future__ import annotations

import re
from pathlib import Path

BACKLOG = Path(__file__).resolve().parent.parent / "docs" / "backlog.md"

SECTIONS = [
    "Brainstorms queued for the PI",
    "Features not yet planned",
    "Deferred defects",
    "Debt",
    "Needs the rig",
    "Waiting on another repository",
]

#: The one-line format, split on its separator rather than matched by one pattern:
#: a field is whatever lies between two ` — `, so a field holding one is a line
#: with too many fields, and says so.
SEPARATOR = " — "
ITEM = re.compile(r"^- \*\*(?P<id>XC-\d{3})\*\* (?P<rest>.*)$")
#: Whatever sits in the bold, well-formed or not, so a malformed ID is reported as one.
ANY_ID = re.compile(r"^- \*\*(?P<id>[^*]+)\*\* ")
#: The origin *starts* with the date it arose. Anywhere would do for a reader, but a
#: link's path often carries a date of its own (`specs/2026-09-28-direct-view-...`),
#: and a check that searched the whole field passed an origin with no date in it.
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}, ")
LINK = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
WAITS = "waits on: "
NEXT_FREE = re.compile(r"\*\*Next free ID: XC-(\d{3})\.\*\*")

PREAMBLE_LIMIT = 25


def _lines() -> list[str]:
    return BACKLOG.read_text().splitlines()


def _first_section(lines: list[str]) -> int:
    return next(n for n, line in enumerate(lines) if line.startswith("## "))


def _section_lines() -> list[tuple[int, str]]:
    """Every line from the first section heading on, with its 1-based number."""
    lines = _lines()
    start = _first_section(lines)
    return [(n + 1, line) for n, line in enumerate(lines) if n >= start]


def _items() -> list[tuple[int, str]]:
    return [(n, line) for n, line in _section_lines() if line.startswith("- ")]


def _fields(line: str) -> tuple[str, list[str]]:
    """The item's ID and its fields: title, origin, waits on."""
    match = ITEM.match(line)
    assert match, f"not an item line: {line!r}"
    return match["id"], match["rest"].split(SEPARATOR)


# ---------------------------------------------------------------------------
# The file's skeleton
# ---------------------------------------------------------------------------


def test_the_six_sections_exist_in_order_and_no_others():
    """The kind is the section. A seventh heading is a seventh kind, and the point of
    six is that an item's kind is one of them -- not whatever the day's writer
    thought of."""
    headings = [line[3:] for line in _lines() if line.startswith("## ")]
    assert headings == SECTIONS


def test_the_preamble_stays_short():
    """What the file is, its rules, and how to add, close and find an item. A preamble
    that grows is the narrative this file exists to keep out, arriving at the top."""
    lines = _lines()
    preamble = lines[: _first_section(lines)]
    while preamble and not preamble[-1].strip():
        preamble.pop()
    assert len(preamble) <= PREAMBLE_LIMIT, (
        f"the preamble is {len(preamble)} lines; it may be {PREAMBLE_LIMIT}"
    )


def test_nothing_but_items_and_blank_lines_sits_in_a_section():
    """No prose, no sub-headings, no continuation lines. An item that needs more than
    one line has reasoning in it, and the reasoning belongs where it arose."""
    stray = [
        (n, line)
        for n, line in _section_lines()
        if line.strip() and not line.startswith("## ") and not line.startswith("- **XC-")
    ]
    assert stray == [], f"lines in a section that are not items: {stray}"


# ---------------------------------------------------------------------------
# Each item
# ---------------------------------------------------------------------------


def test_every_item_is_one_line_in_the_format():
    """`- **XC-NNN** <title> — <origin> — waits on: <what>`, exactly three fields, a
    title that is one sentence."""
    bad = []
    for n, line in _items():
        match = ITEM.match(line)
        if not match:
            bad.append((n, "not `- **XC-NNN** ...`"))
            continue
        fields = match["rest"].split(SEPARATOR)
        if len(fields) != 3:
            bad.append((n, f"{len(fields)} fields separated by ' — ', not 3"))
            continue
        title = fields[0].strip()
        if not title or not title.endswith("."):
            bad.append((n, "the title is not one sentence ending in a period"))
    assert bad == [], bad


def test_ids_are_well_formed_and_unique():
    """An ID is how a commit closes an item and how another item waits on it, so two
    items with one ID make both of those ambiguous."""
    ids = [m["id"] for _, line in _items() if (m := ANY_ID.match(line))]
    malformed = [i for i in ids if not re.fullmatch(r"XC-\d{3}", i)]
    assert malformed == [], f"IDs not of the form XC-NNN: {malformed}"
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    assert duplicated == [], f"IDs used twice: {duplicated}"


def test_the_next_free_id_is_above_every_id_in_use():
    """IDs are never reused. A closed item's line is gone, so the file alone cannot say
    which IDs were ever taken; the counter in the preamble can, as long as it only
    goes up."""
    match = NEXT_FREE.search(BACKLOG.read_text())
    assert match, "the preamble must carry **Next free ID: XC-NNN.**"
    ids = [int(m["id"][3:]) for _, line in _items() if (m := ITEM.match(line))]
    assert int(match[1]) > max(ids), (
        f"the next free ID is XC-{match[1]} and XC-{max(ids):03d} is in use"
    )


def test_every_origin_has_a_date_and_a_link():
    """Where an item arose is where its reasoning lives. Without a date nobody can
    tell a week-old deferral from a month-old one; without a link the reasoning is
    either lost or copied here, and a copy is a thing that can disagree."""
    bad = []
    for n, line in _items():
        _, fields = _fields(line)
        origin = fields[1] if len(fields) > 1 else ""
        if not DATE.match(origin):
            bad.append((n, "the origin does not start with its YYYY-MM-DD date"))
        if not LINK.search(origin):
            bad.append((n, "no link in the origin"))
    assert bad == [], bad


def test_every_item_says_what_it_waits_on():
    """An empty field is not an answer, and "nothing" is. What an item waits on is
    what decides whether a session can pick it up today."""
    bad = []
    for n, line in _items():
        _, fields = _fields(line)
        waits = fields[-1]
        if not waits.startswith(WAITS) or not waits[len(WAITS) :].strip():
            bad.append(n)
    assert bad == [], f"items with no 'waits on: ...': lines {bad}"


def test_every_link_into_the_repository_names_a_file_that_exists():
    """A link is the reasoning's address. When a document is renamed or deleted the
    item keeps pointing at nothing, and nothing else would notice."""
    missing = []
    for n, line in _items():
        for target in LINK.findall(line):
            if "://" in target:
                continue
            path = (BACKLOG.parent / target.partition("#")[0]).resolve()
            if not path.exists():
                missing.append((n, target))
    assert missing == [], missing
