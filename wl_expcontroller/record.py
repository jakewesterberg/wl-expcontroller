"""The session record on disk.

Written into `<root>/<YYYY-MM-DD_NN>/expcontroller/`, which `wl-preproc`'s frozen
path contract already reserves for us by name -- **deliberately outside `SYSTEMS`**,
because a member needs a `DONE` marker, an `AcquisitionSystem` row and a timebase
extractor, and *"an experiment controller's log carries no barcode and needs no
alignment."* So we write no marker and never block session-complete detection, and
our alignment comes entirely from the codes we strobe.

**Streamed, never accumulated.** A crash loses the tail, not the day -- the lesson
`wl-sync` learned when its own recorder held a whole session in memory and a crash
took all of it. That rules out writing Parquet as we go, since a Parquet file is only
valid once closed: JSONL is the durable record and the columnar table is derived from
it at session close, where a crash costs a conversion rather than a session.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

EXPCONTROLLER_DIRNAME = "expcontroller"


@dataclass
class SessionRecord:
    directory: Path
    subject: str
    _trials: TextIO

    @classmethod
    def open(cls, root: Path, session_id: str, subject: str) -> SessionRecord:
        directory = Path(root) / session_id / EXPCONTROLLER_DIRNAME
        directory.mkdir(parents=True, exist_ok=True)
        return cls(
            directory=directory,
            subject=subject,
            _trials=(directory / "trials.jsonl").open("a", encoding="utf-8"),
        )

    def trial(
        self,
        index: int,
        outcome: str,
        params: dict,
        block: str = "",
        condition: str = "",
    ) -> None:
        """One trial's record, flushed before returning.

        **The whole resolved parameter set, per trial** -- not a pointer to "the
        config" (P16). A parameter changed at trial 300 is invisible at analysis time
        unless each trial says what it actually ran with, and that is the single most
        likely way live editing damages a dataset.

        **And the subject on every row**, because two animals routinely work in one
        day while the session directory is keyed on the sync box's day-scoped id
        (S3 §2). Naming it per trial makes a day partition correctly whatever
        `wl-sync` decides about `_02`.
        """
        self._trials.write(
            json.dumps(
                {
                    "index": index,
                    "subject": self.subject,
                    "outcome": outcome,
                    "params": params,
                    "block": block,
                    "condition": condition,
                },
                sort_keys=True,
            )
            + "\n"
        )
        self._trials.flush()

    def snapshot(
        self, layers: dict[str, dict], resolved: dict, versions: dict
    ) -> None:
        """The config a session ran under, layers and all.

        **The precedence chain, not only the resolved values** (S8 §3.4). Recording
        what a parameter *was* loses where it came from, and "why was `fix_hold` 0.3
        that day" is asked months later, when the layers are the only thing that
        answers it.
        """
        (self.directory / "config.json").write_text(
            json.dumps(
                {"layers": layers, "resolved": resolved, "versions": versions},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def parameter_change(
        self, sequence: int, name: str, was: object, now: object, by: str
    ) -> None:
        """One live parameter change, joined to the recording by `sequence`.

        The `PARAM_CHANGE` escape carries that number and nothing else: the values
        live here (S2 §5.2). If the two ever disagree the change cannot be placed on
        the recording clock at all, so the join is the entire point of both halves.

        `by` records the origin -- console, control API, or the task -- because one
        validated write path with an unrecorded actor is only half the guarantee.
        """
        with (self.directory / "parameter_changes.jsonl").open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write(
                json.dumps(
                    {
                        "sequence": sequence,
                        "name": name,
                        "was": was,
                        "now": now,
                        "by": by,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    def refusal(self, name: str, asked: float, by: str, why: str) -> None:
        """A welfare-bounded write the session refused, kept durably (PI,
        2026-09-19).

        **Because telemetry is lossy by design and this is not a telemetry-shaped
        fact.** A refusal reached `link.Refused` and nothing else, so an attempt to
        set a dose above its limit left no trace at all unless a console happened to
        be attached at that moment and happened to still hold the row (S9a §9 caps
        the feed at `link.REFUSAL_HISTORY`). "Somebody tried to give this animal
        four times its volume" is exactly the kind of thing asked months later, and
        it is answered from the record or not at all.

        **Ceiling-bounded names only**, which `taskd.Session._command` decides. A
        mistyped task-parameter name is a slip at a keyboard, not a welfare event,
        and writing every one of those here would bury the rows that matter.

        No `sequence`, unlike `parameter_change`: that number exists to join a
        change to the `PARAM_CHANGE` escape on the recording clock, and a change
        that did not happen strobes nothing. This row says an attempt was made and
        was refused, not when on the recording it sat.
        """
        with (self.directory / "refusals.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"name": name, "asked": asked, "by": by, "why": why},
                    sort_keys=True,
                )
                + "\n"
            )

    def close(self) -> None:
        self._trials.close()

    def __enter__(self) -> SessionRecord:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
