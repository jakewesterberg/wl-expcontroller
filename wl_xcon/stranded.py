"""Sessions an animal was left out of its cage in, found after a restart, and their
returns (P4d-2b spec §6.1: "Nothing is quietly lost to a crash").

**Welfare-critical, the whole module** (`docs/design/architecture.md`). Human review
before merge.

**Found from the record alone.** A session under `--root` is stranded when its
`welfare_notes.jsonl` has a `departure` row with no `returned` row after it: a process
that died, a `wlx run` that ended with `return not recorded`, a `wlx taskd` stopped with
its session open -- each leaves exactly that. **A line that is not a row** -- a crash
mid-write -- **fails closed**, and so does a record this host cannot read as a file: the
session is stranded with its departure unknown, and
its return cannot be taken until the file is repaired by hand, since a departure nobody
can read is one no return can be checked against. **And whether it can be resumed**
(XC-026): `resume.read` is asked, and its refusal kept as `why`.

**Closed under `welfare`'s rules.** `restore` builds a `Welfare` holding only the
recorded departure (`Welfare.restore_departure`) and wraps it in a `Restored`, which
`marks.take_return` takes as it takes a `Session`: not in the future, not before the
departure, confirmed if far. **Restraint is not reconstructed**: its marks are event
codes on the recording, not rows here, and a head is not held fixed by a process that
has died, so the return is checked as a chaired session's is.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from wl_xcon import resume as _resume
from wl_xcon.bounds import Bounds, Exceeded
from wl_xcon.link import Stranded
from wl_xcon.record import WELFARE_NOTES, XCON_DIRNAME, welfare_note
from wl_xcon.welfare import Absent as NoPump
from wl_xcon.welfare import Deployment, Welfare

#: The reason every row written for a stranded session's return carries.
RESTORED = (
    "the service holding this session stopped before its return was recorded; taken "
    "after a restart (P4d-2b spec §6.1)"
)


def find(root: Path) -> list[Stranded]:
    """Every session under `root` whose record holds a departure with no return after
    it, in folder order. A record with a line that is not a row is stranded with its
    subject empty and its departure `None`."""
    root = Path(root)
    if not root.is_dir():
        return []
    found = []
    for notes in sorted(root.glob(f"*/{XCON_DIRNAME}/{WELFARE_NOTES}")):
        session_id = notes.parent.parent.name
        try:
            departure = None
            for line in notes.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row["kind"] == "departure":
                    departure = row
                elif row["kind"] == "returned":
                    departure = None
            if departure is not None:
                left_at = float(departure["now"])
                try:
                    _resume.read(notes.parent, left_at)
                    resumable, why = True, ""
                except _resume.Unresumable as unresumable:
                    resumable, why = False, str(unresumable)
                found.append(Stranded(session_id=session_id, subject=str(departure["subject"]),
                                      left_at=left_at, resumable=resumable, why=why))
        except (ValueError, KeyError, TypeError, OSError):
            # `json.JSONDecodeError` is a `ValueError`; a row that is not an object, or
            # has no kind, is the others; a record this host cannot read as a file -- a
            # folder in its place, no permission -- is an `OSError` (fix round 1 of Task
            # 7: it crashed the service at start). Fail closed.
            found.append(Stranded(session_id=session_id, subject="", left_at=None,
                                  resumable=False, why="its welfare record cannot be read"))
    return found


@dataclass
class Restored:
    """A stranded session read back from its record: just enough to take its return --
    `wall_now`, `return_needs_confirmation`, `returned_to_cage`, as `taskd.Session` has
    them -- and to write the rows a `Session` would."""

    directory: Path
    subject: str
    welfare: Welfare
    wall_now: Callable[[], float]

    def return_needs_confirmation(self, at: float) -> str | None:
        return self.welfare.return_needs_confirmation(at, wall_now=self.wall_now())

    def returned_to_cage(
        self, at: float, confirmed: bool = False, by: str = "", how: str = ""
    ) -> None:
        """`Session.returned_to_cage`'s shape: the far question asked before the mark,
        so a `return confirmed` row is written when one was owed; the rows only after
        `welfare` has taken it."""
        wall_now = self.wall_now()
        far = self.welfare.return_needs_confirmation(at, wall_now)
        self.welfare.returned_to_cage(at, wall_now=wall_now, confirmed=confirmed)
        for kind in ("returned", "return confirmed") if far is not None else ("returned",):
            welfare_note(
                self.directory,
                kind=kind,
                subject=self.subject,
                was=at,
                now=at,
                reason=RESTORED,
                by=by,
                how=how,
                recorded_at=self.wall_now(),
            )


def restore(
    found: Stranded, bounds: Bounds | None, directory: Path, wall_now: Callable[[], float]
) -> Restored:
    """A stranded session, ready for its return: its animal's bounded config (which a
    `Welfare` needs to exist, and whose subject must be the session's), and its recorded
    departure. Refused, with the sentence a person needs, for a record that cannot be
    read or bounds that name another animal.

    **The unreadable record is refused first**, before `bounds` is read: a caller that
    cannot know the animal of a record it cannot read passes `None` for it, and only
    then."""
    if found.left_at is None:
        raise Exceeded(
            f"session {found.session_id}'s welfare record cannot be read: "
            f"{Path(directory) / WELFARE_NOTES} has a line that is not a row, as a "
            f"process that died while writing it leaves one, or is not a file this host "
            f"can read. Its departure is unknown, so no return can be checked against "
            f"it: repair the file by hand -- remove the torn line, keep every whole row, "
            f"and make it a readable file -- then restart wlx taskd"
        )
    if bounds.subject != found.subject:
        raise Exceeded(
            f"session {found.session_id} is {found.subject!r}'s, and the bounded config "
            f"given is {bounds.subject!r}'s"
        )
    welfare = Welfare(
        bounds=bounds, pump=NoPump(), already_today=None, deployment=Deployment.RIG_CHAIRED
    )
    welfare.restore_departure(found.left_at)
    return Restored(Path(directory), found.subject, welfare, wall_now)
