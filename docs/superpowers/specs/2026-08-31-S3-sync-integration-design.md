# S3 — Sync and timing integration

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Parent:** `2026-08-31-controller-architecture-design.md` §3, §12
- **Posture:** this spec mostly **deletes** things from our design. Where `wl-sync` or
  `wl-preproc` already owns a concept, our job is to stop having a second one.

---

## 1. What `wl-sync` actually owns

Read from source at `wl-sync` commit `90b931e` and `wl-preproc` `f7fb10a`, 2026-08-31.

| Thing | Where | Shape |
|---|---|---|
| Session identity | `wl_sync/session.py` | `YYYY-MM-DD_NN`, date plus a two-digit index. **Nothing else.** No subject, no rig. |
| Barcode | `wl_sync/barcode.py` | 32-bit value, 200 ms frame, once per second, 800 ms idle between. One barcode guaranteed in any 2.0 s window. **"The barcode carries identity, not timing."** |
| Log format | `wl_sync/log.py` | One JSON header, then `E,tick,gpio,level` edges, `W,tick,word` strobed event words, `B,tick,value` emitted barcodes |
| Day layout | continuous-recording design §3 | `<out>/YYYY-MM-DD_NN/` with `manifest.json` and `seg-NNN.log` per process run |
| GPIO map | `wl_sync/pins.py` | Event data on GPIO 0–15, strobe 16, barcode out 17, and eight individually-captured edge pins 20–27 |

**The sync box independently records every event word we strobe** (`W` records, captured by
PIO). So each code we emit exists in at least three places: the sync box log, the NI digital
lines into SpikeGLX, and our own log.

**Consequence, and it simplifies us:** our log is not the timing record and does not need to
be. It carries *meaning* — parameters, decisions, task state — keyed to codes whose timing two
other systems already hold. This is S2's identity-versus-content rule applied one level up.

---

## 2. The word "session" means three different things

This is the substantive finding, and papering over it would have produced a directory nobody
could ingest.

| Term | Defined by | Meaning | Scope |
|---|---|---|---|
| **Session** | `wl-sync` | *"A day is one session, hence `_01`; a restart joins that directory as a new segment rather than minting `_02`."* | A **day** |
| **Session** | `wl-preproc` | element-session's `Session`, keyed `(subject, session_datetime)`; `eye.py` reasons about "a ~40 minute session" | A **subject's run** |
| **Block** | `wl-preproc` `core.Block` | *"One run of one task, mirroring wl.works `animal_session_block`"*, keyed `(subject, session_datetime, block_id)` with `task_type` | A **task run** |

And `wl-preproc/contracts/paths.py` keys the session **directory** on
`wl_sync.session.SessionId` — the day-scoped one — while its `Session` **table** is
subject-scoped. Those coincide only if exactly one subject works per day.

**Two animals will routinely work in one day on one rig** (PI, 2026-08-31). So they do not
coincide, and `wl-sync`'s *"a day is one session, hence `_01`"* does not hold for this lab.
`_NN` is load-bearing: something must mint `_02`, and nothing currently does. This is no longer
an ambiguity to note — it is a gap with a known answer on one side, and the amendment in §9
says so rather than asking.

Our own posture is unchanged and was chosen to survive exactly this:

1. Our outputs live under the **sync box's session id**, because the directory contract says so.
2. **Every record we write names its subject explicitly**, so a day containing two subjects
   partitions correctly with no renaming and no inference.
3. Our own documents stop saying "session" loosely. **Day**, **session** (a subject's run), and
   **block** (a run of one task) are the three words, and §5 fixes them in the parent spec.

Raised with `wl-sync` and `wl-preproc` as an amendment (§9).

---

## 3. What we delete

| Our design said | Reality | Action |
|---|---|---|
| taskd mints a sync barcode | `wl-sync` owns the codec and emits it | **Deleted.** We never emit a barcode. |
| We define sync conventions | `wl-sync` owns the fabric | **Deleted.** §4 states our obligations to it instead. |
| Session identity is ours | `wl-sync` mints it; the directory is keyed on it | **Deleted.** We consume it. §6 covers how we learn it. |
| "Session summary endpoint" | Corrected already in the wl-works amendment | Already deleted |
| Our JSONL is the timing record | Three systems hold event timing | **Weakened deliberately.** Our log carries meaning, not truth. |
| `wl-2027-01-14-A-001` as a session id | Fabricated; the real form is `YYYY-MM-DD_NN` | **Corrected** in the parent spec |

---

## 4. Our obligations to the sync fabric

1. **Strobe correctly.** 16 data bits plus strobe, meeting the setup and hold the PIO capture
   requires. Verified on the event-path mule before the full board exists.
2. **Never emit a barcode**, and never derive time from one. We read event codes back only
   through analysis, never in the loop.
3. **Mirror every scientifically meaningful decision as a code**, so the sync box's `W` record
   and the NI record are both complete without our files.
4. **Photodiode patches drawn correctly and continuously** — the flip patch must alternate on
   *every* refresh, because the sync box and our own dropped-frame detection both read it as a
   frame clock (S0 §5.4, parent §11.5).
5. **Emit nothing during an escape payload.** S2 §6.3: escape, payload words and checksum are
   one uninterruptible sequence, on every code path including an abort.

---

## 5. The session directory — already reserved for us

`wl-preproc/contracts/paths.py` is a **frozen interface** and it already names us:

```
<root>/<YYYY-MM-DD_NN>/
├── session_manifest.yaml
├── syncbox/   spikeglx/   rhs/   ohdpi/   bcam/     <- SYSTEMS, each with a DONE marker
└── expcontroller/                                    <- ours, EXPCONTROLLER_DIRNAME
```

Their comment: *"Named for the ROLE, not the vendor … MonkeyLogic writes a `.bhv2` here today,
and `wl-expcontroller` will write whatever it writes."*

**We are deliberately not a `SYSTEMS` member**, and that is load-bearing rather than cosmetic.
`SYSTEMS` members need a `DONE` marker, an `AcquisitionSystem` row, and a timebase extractor —
`timebase/extract.py` asserts `set(EXTRACTORS) == set(SYSTEMS)` as a completeness claim. Their
reasoning: *"An experiment controller's log carries no barcode and needs no alignment, so
adding it there would demand an extractor that cannot exist."* Discovery iterates `SYSTEMS`
explicitly, so our directory is simply ignored by it.

**Two consequences for us:**

- **We write no `DONE` marker** and are not part of session-complete detection. Our absence
  never blocks ingest. This contradicts the parent spec §12.2, which promised one; corrected.
- **Our alignment comes entirely from the codes we strobe**, which the syncbox and spikeglx
  extractors carry. That is the whole reason we need no extractor, and it is why obligation 3
  in §4 is not optional.

---

## 6. What we must be told, and by whom

| We need | Source | Mechanism |
|---|---|---|
| The day's session id `YYYY-MM-DD_NN` | `wl-sync` | **Open — §9 amendment.** The sync box mints it and nothing currently offers it to another host. |
| Subject | wl-works | The `prepare-session` push (S0/parent §12.3) |
| Planned blocks and their task types | wl-works' session planner | Same push |
| Probe serials, insertion numbers, `trajectory_id` | wl-works | Same push |

**The sync box does not currently expose its session id.** We could derive `YYYY-MM-DD` from
the date, but `_NN` is the sync box's to mint and guessing it would create a second
authority — exactly the failure this spec exists to avoid. Amendment in §9.

---

## 7. The constraint nobody would have predicted

> `core.Block`: *"block rows are authored by wl.works' session planner and wl-preproc never
> writes them; it **cross-validates and quarantines on absence**."*

**So a block we run that wl.works did not plan quarantines the session at ingest.**

That collides directly with D9's live structure editing. Changing condition weights or array
geometry within a task is fine — it does not create a block. **Changing task type mid-session
does**, and so does inserting an unplanned calibration block.

Three consequences, and the third is the one that keeps flexibility:

1. **Block structure is planned in wl.works before a session**, not invented at the rig.
2. **Calibration uses both mechanisms** (PI, 2026-08-31), which is what `wl-preproc`'s own
   docstring calls them: *"complementary, not alternatives."* A **planned** calibration block
   opens the session — a dedicated block "reliably supplies six well-spread targets," and that
   is what decides whether a session reaches the second-order calibration rung at all — and
   **in-task `CALIBRATION_START`/`CALIBRATION_END` epochs** top it up and track drift through
   the day. The planned block is a coordination cost: wl.works' session planner must plan one
   for every session, or ingest quarantines it. Added to the wl-works amendment.
3. **The measured boundary is ours to emit and theirs to compare.** `trial.Block` holds the
   measured boundary, `core.Block` holds wl.works' assertion, and disagreement is its own
   tier-D condition rather than a silent reconciliation. So an unplanned block is *visible*, not
   destructive — but it degrades the session's timing tier, which is a real cost.

---

## 8. Photodiode patches, cameras, and reconstruction

**Patch roles are fixed in copper** (`wl-sync` breakout spec §3.1): `A_PD1` the task patch,
`A_PD2` the flip patch alternating every refresh. Both reach us as digital comparator edges and
reach the recorders as edges plus analog copies.

**Placement is the open physical question.** Both patches must sit outside both eyes' viewports
on the split screen, or the flip patch is a flickering distractor in one eye's field. Candidates
are the septum strip and a screen edge outside the mirror-visible region. **This is decided
against the real optics, with `wl-sync`, before the mirrors are mounted** — and the 57 cm
viewing distance from S0 §5.2 must be fixed first, since it sets what is visible.

**Cameras** take the barcode as a timebase to record, not a trigger — they free-run, and the
sync box captures their `ExposureActive` strobes on GPIO 26/27. **We do not trigger cameras and
do not set their rate.**

**Reconstruction (V6)** round-trips a synthetic multi-stream day: sync box `E`/`W`/`B` records,
NI digital lines, our own log, and a known ground truth, recovering every event on the shared
clock exactly. It runs in CI once code exists. The synthetic generator in `wl-preproc/synth/`
already emits SpikeGLX and RHS sessions with planted ground truth and three deliberately
different tick origins; our generator should feed the same harness rather than build a second.

---

## 9. Amendments this opens

Against **`wl-sync`** (drafted at `docs/pending-wl-sync-amendments.md`):

1. **Expose the session id to other hosts on the rig.** It mints `YYYY-MM-DD_NN` and nothing
   else can learn it without guessing `_NN`.
2. **Say what mints `_02`.** Two animals will routinely work in one day on one rig, so a day is
   not one session and the continuous-recording design's *"a restart joins that directory as a
   new segment rather than minting `_02`"* needs a companion rule for what does mint it.

Against **`wl-preproc`** (appended to the existing amendment file): the same day/session
question, from their side.

---

## 10. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | How taskd learns the session id | every output path |
| 2 | ~~Day versus subject-session~~ **Answered: two animals routinely.** Remaining: what mints `_02`, which is `wl-sync`'s to say | directory layout under two subjects |
| 3 | Photodiode patch placement against the real optics | rig build |
| 4 | ~~Calibration blocks versus in-task epochs~~ **Answered: both.** Remaining: wl.works planning a calibration block per session | S5, S8, wl-works |
| 5 | Whether our synthetic generator feeds `wl-preproc`'s harness or its own | V6 |
