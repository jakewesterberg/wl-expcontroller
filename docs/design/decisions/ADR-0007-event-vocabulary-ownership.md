# ADR-0007: Ownership of the event vocabulary

- Status: Proposed
- Date: 2026-08-31
- Deciders: Jake (PI)

## Context

Two repositories claim the event vocabulary and their claims contradict.

`wl-mllib/wl.yaml` publishes `task-event-vocabulary`, states *"Nothing is allocated yet,"*
and says *"wl-preproc reads event handling from here rather than defining it."*

`wl-preproc/wl_preproc/contracts/events.py` is a **frozen interface** (their design spec
§3.5 item 4) that defines the range allocation, the session/block/trial markers, a task-type
namespace, four escapes with declared payload word counts, an XOR checksum, offset-binary
degree encoding, and a decoder — all carrying *"values are frozen and never renumbered"*
warnings, because a renumbering silently relabels every block in every prior recording.

`wlo validate` cannot detect this. It verifies that a published artifact name resolves to
exactly one publisher, which it does; it has no way to know a description is false. The
contradiction was found by reading both repositories, which is the discipline `wl-sync`'s
conventions already require and which this project came close to skipping — S2 was scoped as
designing an allocation that already existed.

wl-expcontroller must emit this protocol, and needs codes that neither repository has
allocated. It cannot proceed while ownership is ambiguous.

## Decision

Ownership splits on **decodability versus meaning**. If getting it wrong makes the recording
*undecodable*, it belongs to `wl-preproc`. If it makes the recording *uninterpretable*, it
belongs to `wl-mllib`.

| Range / artifact | Owner |
|---|---|
| Framing, escapes, checksum, payload word counts, DVA encoding | `wl-preproc` |
| `Marker` 1–255 — session, block and trial structure | `wl-preproc` |
| `TaskEvent` 256–4095 — lab-wide task-event semantics | `wl-mllib` |
| `TaskTypeCode` 100+ — lab-defined task identities | `wl-mllib` |
| Task-specific / condition 4096–32767 | `wl-mllib` |

Consequences of the rule, adopted with it:

1. **No value is ever renumbered.** `TaskEvent`'s existing 256–259 transfer as
   already-allocated. Ownership moving is not permission to renumber.
2. **wl-expcontroller allocates nothing itself.** Codes come from `wl-mllib`; a task naming
   an unregistered code is refused at load time.
3. **New escapes are amendments**, because they live in the frozen layer. New task events
   are not. This is why the allocation rule in S2 §4 — codes carry identity and timing, the
   session record carries content — is load-bearing rather than stylistic: it keeps almost
   every addition out of the frozen layer.
4. **We write no second decoder.** Conformance is tested by round-tripping our emitted
   streams through `wl-preproc`'s own `decode_stream`.

## Alternatives considered

- **Move the whole vocabulary to `wl-mllib`, as its manifest already claims**, with
  `wl-preproc` re-exporting it under a CI diff the way it already re-exports `wl-sync`'s log
  header. Cleanest ownership story and it honours the declared contract. Rejected: it means
  relocating a frozen interface out of a repository with 980 tests built on it, while that
  repository is under active development — high cost and real risk, for a tidier line in a
  manifest.
- **Leave ownership ambiguous and conform to whatever exists.** Rejected: the ambiguity is
  what produced two contradictory manifests, and a third consumer would inherit it. It also
  leaves nobody able to answer where a new code goes.
- **wl-expcontroller allocates its own codes.** Rejected outright: it makes a third
  definition and forfeits the load-time refusal that is this design's cheapest guardrail
  against model-authored task files (pitfalls P15).

## Consequences

- `wl-mllib/wl.yaml`'s published artifact narrows to the three ranges it actually owns and
  gains a `consumes` edge for the codec. Corrected in the same change as this ADR.
- Three amendments are opened against `wl-preproc`
  (`docs/pending-wl-preproc-amendments.md`): one new escape, the ownership split recorded in
  their docstring plus the codec declared as a published artifact so the registry can see it
  at all, and a premise in their DVA comment that assumed MonkeyLogic would be the
  controller.
- **S2's open item 1 remains open until `wl-preproc` agrees**, because `TaskEvent` 256–4095
  is the one range this ADR moves rather than merely describes. If they decline, our
  allocations go to 4096–32767 and nothing else in this decision changes.
- The parent architecture spec §6's claim that codes are "allocated in `wl-mllib`" is true of
  the ranges a task uses and false of the protocol. Corrected there.
