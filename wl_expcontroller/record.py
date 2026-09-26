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
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

EXPCONTROLLER_DIRNAME = "expcontroller"

#: How many refusal rows one session writes before it stops writing them (PI,
#: 2026-09-19).
#:
#: **A bound on an untrusted peer's reach into the record, and on the write load
#: between trials.** `taskd.Session._command` records a row for every refused
#: welfare-bounded write, and nothing about that is rate-limited by a human: a
#: console looping on a rejected volume produces one per packet, each one a file
#: open, an encode and a flush -- in the inter-trial interval, where the session has
#: work to do. Unbounded, the file grows with the peer and so does the work.
#:
#: **Deliberately equal to `link.REFUSAL_HISTORY`**, and a test in `test_record.py`
#: keeps them equal. Two constants rather than an import because the durable record
#: must not depend on the console link -- the console is a view, never a source --
#: but a session that keeps fifty refusals in memory and a different number on disk
#: is two policies nobody chose.
#:
#: **The file keeps the oldest rows; the in-memory feeds keep the newest.** That is
#: the decision, not an oversight. A console answers "what is happening now". A
#: record answers "what happened", and a flood is a fault or a misbehaving console
#: while a genuine mistake appears early, when a person is typing -- so the last
#: fifty of a thousand would be exactly the rows no human wrote.
REFUSAL_LOG_LIMIT = 50

#: Operator acts on a welfare input that is not a parameter and not a refusal (PI,
#: 2026-09-20). One row per act, in the session directory.
#:
#: **Why its own file rather than one of the two beside it.** A row in
#: `parameter_changes.jsonl` carries a `sequence` whose entire purpose is to join it
#: to a `PARAM_CHANGE` escape on the recording clock -- and the out-of-cage marks are
#: deliberately *not* event-coded (PI, 2026-09-20, closing S8 open item 8), so such a
#: row would look alignable and be nothing of the kind. `refusals.jsonl` is for writes
#: that did **not** happen, is capped at `REFUSAL_LOG_LIMIT` against a flooding
#: console peer, and drops its newest rows; a confirmed or amended departure happened,
#: is one per session, and must not be droppable.
WELFARE_NOTES = "welfare_notes.jsonl"


def welfare_note(
    directory: Path,
    *,
    kind: str,
    subject: str,
    was: float,
    now: float,
    reason: str,
    by: str,
    how: str,
    recorded_at: float,
) -> None:
    """One person's act on a welfare input, written where it can be found later.

    **A module function rather than a `SessionRecord` method, because it is written
    before the record exists.** The departure time is confirmed or amended in
    `wlx run` *before* `Session.run` opens the record: the mark has to be settled
    before `welfare.preflight`, which is what lets the session refuse rather than
    start and stop. Writing it at the moment it happened also means it survives
    everything that can refuse the session afterwards -- a blocking finding in the
    task, a preflight refusal -- which is exactly when someone will want to know what
    the operator was told and what they did about it.

    **`was` and `now` are POSIX instants and each is written twice**, once as the
    number and once as local clock time with its zone. The question this row answers
    is asked by a person months later, and `1768394700.0` does not answer it; the
    float is kept beside it so nothing has to re-parse the text.

    Uncapped, unlike `refusal`: the party generating these is an operator typing at a
    prompt, not a console peer looping on a rejected volume.

    `reason` and `by` are written as given. **`welfare.amend_mark` is what refuses a
    blank pair**, so the rule has one home and the console path that P4d-2 adds cannot
    reach the record around it.
    """
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / WELFARE_NOTES).open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "kind": kind,
                    "subject": subject,
                    "was": was,
                    "was_local": _local(was),
                    "now": now,
                    "now_local": _local(now),
                    "reason": reason,
                    "by": by,
                    "how": how,
                    "recorded_at": recorded_at,
                    "recorded_at_local": _local(recorded_at),
                },
                sort_keys=True,
            )
            + "\n"
        )


def _local(posix_seconds: float) -> str:
    """A POSIX instant as this host's local clock time, with its zone named.

    The zone **at that instant**, not at now, for the reason `wlx run`'s own
    session-start line resolves it that way: a departure made before a daylight-saving
    change and read after one would otherwise be labelled with the wrong offset, and
    that is the one hour a year the label carries information.
    """
    when = time.localtime(posix_seconds)
    return f"{time.strftime('%Y-%m-%d %H:%M:%S', when)} {time.strftime('%Z', when)} local"


@dataclass
class SessionRecord:
    directory: Path
    subject: str
    _trials: TextIO
    #: Refusal rows written, and refusals seen after the limit. `close` turns a
    #: non-zero drop count into one notice row -- see `refusal`.
    _refusals_written: int = 0
    _refusals_dropped: int = 0

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

    def refusal(
        self,
        name: str,
        asked: float,
        by: str,
        why: str,
        trial_index: int,
        session_seconds: float,
    ) -> None:
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

        **`trial_index` and `session_seconds` place it, and nothing else does.** A
        row whose own reason for existing is "this is asked months later" has to say
        *when* within the session, or a reader has only an ordering. `session_seconds`
        is `taskd.Session.now()` -- the frame-derived clock the trials are timed on,
        not a wall clock: a wall clock here would invite someone to align a refusal to
        the neural recording, which is exactly what `parameter_change`'s `sequence`
        exists to do properly and this cannot. (It was also the clock `chair_seconds`
        and the out-of-cage ceiling read, until P4d-2a moved every welfare duration to
        the wall -- spec §10. This row stays on the frame clock: it places a refusal
        among trials, and bounds nothing.)

        No `sequence`, unlike `parameter_change`: that number exists to join a
        change to the `PARAM_CHANGE` escape on the recording clock, and a change
        that did not happen strobes nothing.

        **Bounded at `REFUSAL_LOG_LIMIT`, oldest kept** (PI, 2026-09-19). Past the
        limit this returns having touched no file at all, which is the half of the
        bound that is about the inter-trial write load rather than the file's size.
        What was dropped is counted and `close` writes one notice row for it; see
        that constant for why the oldest are the ones worth keeping.
        """
        if self._refusals_written >= REFUSAL_LOG_LIMIT:
            self._refusals_dropped += 1
            return
        self._refusals_written += 1
        with (self.directory / "refusals.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "name": name,
                        "asked": asked,
                        "by": by,
                        "why": why,
                        "trial_index": trial_index,
                        "session_seconds": session_seconds,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    def close(self) -> None:
        """Release the trial handle, and account for a truncated refusal log first.

        **The notice row is written here because only here is the count final.** It
        carries `truncated`, which no refusal row does, so the two are told apart by
        shape rather than by position. A session nobody flooded gets no notice at
        all: evidence of a cap that appeared on every session would stop being read.

        A crash hard enough to skip `close` leaves the kept rows and no notice --
        the same tail-loss this file's module docstring accepts everywhere else, and
        the live console had the count in `Telemetry.refusals_dropped` throughout.
        """
        if self._refusals_dropped:
            with (self.directory / "refusals.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write(
                    json.dumps(
                        {
                            "truncated": True,
                            "kept": self._refusals_written,
                            "dropped": self._refusals_dropped,
                            "limit": REFUSAL_LOG_LIMIT,
                            "why": (
                                "this session refused more welfare-bounded writes "
                                "than the record keeps; the earliest are kept "
                                "because a flood is a fault and a genuine mistake "
                                "comes first"
                            ),
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
        self._trials.close()

    def __enter__(self) -> SessionRecord:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
