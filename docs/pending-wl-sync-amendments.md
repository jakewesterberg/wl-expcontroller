# Amendments to wl-sync

**Two are open, both opened 2026-08-31** while designing S3
([`superpowers/specs/2026-08-31-S3-sync-integration-design.md`](superpowers/specs/2026-08-31-S3-sync-integration-design.md)).
Read against `wl-sync` at the commit `wl-preproc` pins, `90b931e`.

Written here rather than applied there, following that repository's own convention. Neither
asks for a change to the barcode codec, the log format, or session identity's *form* — those
are `wl-sync`'s and this project consumes them unchanged, having deleted its own duplicates of
all three (S3 §3).

---

# OPEN — the session id is minted here and cannot be learned from anywhere else

## The finding

`wl_sync/session.py` mints `YYYY-MM-DD_NN` and its own docstring states the consumers:
*"Everything downstream — the rig directory layout, the ELN, wl-preproc — consumes it."*
`wl-preproc/contracts/paths.py` imports `SessionId` from this package and keys the whole session
directory on it, and `wl-expcontroller` writes into `expcontroller/` beneath that directory.

**But nothing offers the value to another host.** The date half is derivable; `_NN` is not. A
task controller starting up has no way to know which session it is in.

## Why guessing is not acceptable

`_NN` exists precisely so a day can be indexed, and the continuous-recording design rules that
*"a day is one session, hence `_01`; a restart joins that directory as a new segment rather than
minting `_02`."* If a task PC assumed `_01`, it would be a **second authority on session
identity** — right almost always, and silently wrong exactly when the day is unusual, which is
when a lost recording hurts most. That is the same class of error S3 spent its whole length
deleting from wl-expcontroller's own design.

## The ask

Some way for a rig host to read the current session id from the sync box. The smallest thing
that would work:

- the day directory name is already on disk and already authoritative, so **if the sync box's
  output root is reachable from the task PC**, reading the newest `YYYY-MM-DD_NN/` directory is
  sufficient and needs no new code at all; or
- a one-line file, or a trivial read-only endpoint, if the root is not shared.

**We have no preference and this is your call.** The requirement is only that the value be
*readable* rather than *inferred*, and that the sync box stay the only thing that mints it. If
the answer is "the output root is shared, read the directory," say so and this amendment closes
with no code written.

---

# OPEN — a day is not one session on these rigs, so something must mint `_02`

## The finding

Three definitions of "session" are live across two repositories:

| Term | Where | Meaning |
|---|---|---|
| Session | `wl-sync` continuous-recording design §3 | *"A day is one session, hence `_01`"* |
| Session | `wl-preproc` `pipeline.Session` (element-session) | keyed `(subject, session_datetime)`; `schema/eye.py` reasons about "a ~40 minute session" |
| Block | `wl-preproc` `core.Block` | *"One run of one task, mirroring wl.works `animal_session_block`"* |

And `wl-preproc` keys the session **directory** on this package's day-scoped `SessionId` while
its `Session` **table** is subject-scoped. Those coincide only if exactly one subject works per
day.

**The rig owner has confirmed that two animals will routinely work in one day on one rig**
(2026-08-31). So they do not coincide, and the continuous-recording design's *"a day is one
session, hence `_01`"* does not hold. This is not a question about whether the case can arise;
it is the ordinary case, and nothing currently mints `_02`.

## Why it reaches you

Because this package mints the identity, so whichever answer is right is a fact about
`YYYY-MM-DD_NN`, not about anyone's table. And because the rig owner is the only person who
knows whether two animals will ever work in one day.

## What wl-expcontroller did meanwhile

Adopted the interpretation that is correct under **either** resolution, so nothing here is
blocked on an answer: outputs live under the sync box's session id, and **every record names its
subject explicitly**, so a day containing two subjects partitions correctly with no renaming and
no inference. Our own documents now use three distinct words — day, session, block — rather than
overloading one.

## `wl-preproc`'s own contract already answers it

`wl-preproc/contracts/manifest.py::SessionManifest` sits at the root of the session directory
and carries **exactly one `subject`** — a single string, not a list — beside the `session_id` it
validates against your form. **A directory can describe one subject and no more.** So with two
animals in a day, the session id must change when the subject changes; there is no representation
in which it does not.

That is not our preference, it is a consequence of a frozen interface in a third repository, and
it holds whatever anyone here would have chosen.

## The ask

**A subject change mints `_02`.** The remaining question is mechanical rather than definitional:
the sync box runs continuously across both animals and cannot know when one leaves the chair, so
**something has to tell it.** Whether that is the task PC, wl.works, or a person pressing a
button on the box is yours to decide — but whatever it is, it is also the moment the task PC
learns the new id, so the two amendments share one mechanism.

This is now a **prerequisite for the first amendment**, not a companion to it: if `_02` can
exist, then reading "the newest `YYYY-MM-DD_NN/` directory" is not sufficient for a task PC to
learn which session it is in, because the newest directory may belong to the animal that just
finished.

---

# Not an ask — three things we now depend on, recorded so a change here is visible

None of these need to change. They are written down because `wl-expcontroller` now relies on
them and `wlo dependents wl-sync` would not otherwise show it:

1. **The sync box independently records every event word we strobe** (`W` records via PIO
   capture). This is why our own log is deliberately *not* a timing record and carries meaning
   only — a simplification we took on the strength of your capture, not ours.
2. **The barcode carries identity, not timing**, and one frame is guaranteed in any 2.0 s
   window. We never emit one and never derive time from one.
3. **Cameras free-run and the box records their `ExposureActive` strobes** on GPIO 26/27. So
   `wl-expcontroller` does not trigger cameras and does not set their rate — a role it might
   otherwise have assumed.
