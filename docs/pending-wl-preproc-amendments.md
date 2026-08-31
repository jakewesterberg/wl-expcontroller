# Amendments to wl-preproc

**Three are open, all opened 2026-08-31** while designing S2
([`superpowers/specs/2026-08-31-S2-event-vocabulary-design.md`](superpowers/specs/2026-08-31-S2-event-vocabulary-design.md)).
Written here rather than applied there, following that repository's own convention for
`wl-works`. Read against `wl_preproc/contracts/events.py` at commit `f7fb10a`.

**Two of the three are free, and the third is small.** Items 2 and 3 change no numbers and
no wire behaviour — one records an ownership split in a docstring, the other corrects a
premise. Only item 1 touches the frozen interface, and it adds one escape without altering
any existing value.

**Note on timing.** `wl-preproc` was committed to on 2026-08-31 and a
`spec/second-order-calibration` branch merged the same day, so this is written against a
moving target. If any of it collides with work in flight, this document is the losing side.

---

# OPEN — one new escape: `PARAM_CHANGE`

## The ask

```python
class Escape(IntEnum):
    ...
    PARAM_CHANGE = 0x8005

PAYLOAD_WORD_COUNTS[Escape.PARAM_CHANGE] = 2   # uint32 change sequence number, high word first
```

No existing value changes. The payload is a **pointer, not content**: a monotonic sequence
number that joins to a record in the session directory carrying what actually changed.

## Why it has to be in the stream at all

wl-expcontroller supports live parameter editing between trials — changing, for example, a
search array's eccentricity from 0 to 10 degrees while the animal is working. That is a
stated must-have, and it is also the most likely way this controller quietly damages a
dataset: a change made at trial 300 is invisible at analysis time unless it was recorded.
Our own risk register calls it P16.

Every trial already carries a complete resolved parameter snapshot in the session record, so
the *content* is safe. What the snapshot cannot give is **the moment on the recorded clock**
where the discontinuity falls. A `SimpleEvent` code would supply the moment but not which
change it was, which is ambiguous the instant two parameters move in one inter-trial
interval.

## Why a pointer and not the values

Following this file's own reasoning for `BLOCK_START`: content belongs in the stream when the
recording must stay interpretable without external files. A block's task type qualifies —
"self-describing in the recording even when the ELN is wrong or late." Parameter values do
not: they always travel with the session directory, and encoding floats into 16-bit words to
duplicate them would cost precision and buy nothing. Two words for a uint32 also reuses the
exact shape `TRIAL_NUMBER` and `CONDITION` already use, so it needs no new payload idiom.

## What it costs

One enum value, one dictionary entry, and one line in the schema export. `decode_stream`
needs no change — it reads `PAYLOAD_WORD_COUNTS` and checksums generically.

---

# OPEN — record the ownership split, because two manifests currently contradict

## The finding

`wl-mllib/wl.yaml` publishes `task-event-vocabulary` and states *"Nothing is allocated yet"*
and *"wl-preproc reads event handling from here rather than defining it."* Neither is true:
`contracts/events.py` defines the range allocation, the markers, the task-type namespace, the
escapes and the framing, and freezes them.

`wlo validate` cannot catch this. It checks that a published artifact name resolves to exactly
one publisher — and it does. It has no way to know the description is false.

## The ruling taken on our side (2026-08-31)

Ownership splits on **decodability versus meaning**: if getting it wrong makes the recording
*undecodable* it is wl-preproc's; if it makes the recording *uninterpretable* it is
wl-mllib's.

| Range / artifact | Owner |
|---|---|
| Framing, escapes, checksum, payload word counts, DVA encoding | **wl-preproc** |
| `Marker` 1–255 | **wl-preproc** |
| `TaskEvent` 256–4095 | **wl-mllib** |
| `TaskTypeCode` 100+ | **wl-mllib** |
| Task-specific / condition 4096–32767 | **wl-mllib** |

## The ask

Nothing moves and nothing is renumbered. `TaskEvent`'s four existing values
(`FIXATION_ACQUIRED` 256 … `CALIBRATION_END` 259) **stay exactly where they are** — ownership
moving is not permission to renumber, and this file's own warning about renumbering silently
relabelling prior recordings applies with full force.

What is asked is that the split be **stated** in `TaskEvent`'s docstring, so the next person
to add a code knows which repository allocates it. `wl-mllib`'s manifest is being corrected on
our side in the same change.

If you would rather keep `TaskEvent` 256–4095, say so and we will allocate ours in
4096–32767 instead. The layering matters more than which side of it that range falls on.

## And one thing the registry cannot see at all

`wl-preproc/wl.yaml` publishes seven artifacts — session manifest, job request, health
response, behaviour camera sidecar, done marker, the syncbox log header mirror, and the NWB
session. **The event codec is not among them.** So the most load-bearing cross-repo contract
in the recording path is invisible to `wlo`: nothing can ask who owns it, nothing appears in
`wlo dependents`, and a change to it notifies nobody.

Declaring it — something like `name: event-code-protocol`, `kind: python-model`, `at:
wl_preproc/contracts/events.py`, `stability: stable` — costs one manifest entry and makes the
edge visible. We have deliberately **not** added a matching `consumes` entry on our side yet,
because consuming an artifact nobody publishes is a `V014` warning rather than a recorded
dependency. Ours lands the moment yours does.

---

# OPEN — the DVA comment's premise, under ADR-0005

## The finding

`encode_dva`'s comment reasons about why positions are transmitted in degrees rather than
pixels:

> "The task already knows the geometry because it renders the stimulus, and MonkeyLogic holds
> `ScreenInfo.PixelsPerDegree`."

**The conclusion is right and nothing needs to change on the wire.** But under our ADR-0005,
MonkeyLogic will not be deployed as the working controller — wl-expcontroller is the day-one
stack, and the MonkeyLogic swap is maintained only at the rig-contract layer.

## The ask

Restate the second clause. The argument survives intact without it, because it never depended
on MonkeyLogic specifically: **whatever renders the stimulus knows the geometry, and the
pipeline deliberately holds none.** wl-expcontroller holds per-eye viewport geometry,
per-display-mode deg/pixel, and a versioned gaze mapping, so it satisfies the premise at least
as well.

One caveat worth carrying across, since it did not exist when that comment was written: our
rigs use a **split-screen mirror stereoscope**, so a single screen carries two viewports with
their own centres and their own folded path lengths, and the display runs in one of two modes
with different deg/pixel. Degrees remain the right unit — more so, not less — but "the"
pixels-per-degree of a rig is not a single number, which is an argument for never putting
pixels on the wire.

---

# OPEN — `read_online_map` needs a reader for a controller that is not MonkeyLogic

## The finding

`eye/calibration.py::read_online_map` takes a `.bhv2` path and parses a MonkeyLogic binary.
`CalibrationSource.ONLINE`'s own docstring already anticipates this: *"The behavioural control
system will change, and whatever replaces MonkeyLogic will also save a calibration."*

Under wl-expcontroller ADR-0005, MonkeyLogic is not deployed, so **there will be no `.bhv2` to
read** and `ONLINE` — the source you rank above carry-forward, because it is the map the animal
was actually held to — would be unavailable for every session.

## The ask

A second reader, for a small text file written into `expcontroller/`. We write it, you read it;
neither side reverse-engineers the other's binary.

Every field below is one you already compute or consume, so the format asserts nothing new:

| Field | Why |
|---|---|
| `model` | `CalibrationModel`: `affine` or `second_order` |
| `coefficients`, per eye | in `basis()` order — `[1, dx, dy]` or `[1, dx, dy, dx², dy², dx·dy]` |
| `raw_definition` | stated explicitly as `CR1 − CR4`, so a future change on either side is loud |
| `targets` | the constellation actually presented, in degrees |
| `conditioning` | as computed by `_conditioning`, so you can check our arithmetic against yours |
| `rms_residual_deg` | as `validate_map` computes it |
| `mapping_version` | ours; every trial cites it, and a recentre or drift correction increments it |

**We fit your basis to your raw vector.** The shape of the map is not ours to design — §2 of our
S5 spec adopts `purkinje_vector` and `CalibrationModel` verbatim rather than defining a second
model that could drift from yours.

## A second, smaller offer: per-trial gaze staleness

`EyeQuality` holds `tracking_loss_fraction` and `blink_rate_hz` per eye, described as *"a lower
bound on how much of a session is unusable."* We can supply a third quantity of the same kind,
which the recording alone cannot give you.

Every gaze decision we make records **how stale the sample it used was** — the tracker's own
`DataQuality` column says detection succeeded, but not that the sample the controller acted on
was fresh. When a stall overlaps a gaze-contingent epoch the trial now proceeds and is marked,
rather than aborting, so a per-trial staleness summary is what keeps that decision honest: it
arrives as a column an analysis must actively drop rather than a flag it can miss.

Offered rather than asked for. If it does not belong in `EyeQuality` it will sit in our own
behavioural table and you can ignore it.

## One thing your conditioning table changed on our side

Your measured constellations (`MIN_CONDITIONING`, and the table above it) show a **ring of eight
scoring 0.0000 on the second-order basis** — degenerate despite having more points than the fit
needs, because points on a circle make the constant, `dx²` and `dy²` columns linearly dependent.

A ring is the intuitive calibration pattern, and adopting it would have silently foreclosed the
second-order rung for every session. Our calibration block now presents a **3×3 grid** and
computes conditioning online, refusing to complete on a degenerate constellation rather than
discovering it in your pipeline. Recorded here because that table is doing work outside your
repository now, and a change to it would reach us.

---

# Not an ask — one consequence recorded

`contracts/events.py` states that Intan RHS receives the strobe only, because its 16 digital
inputs cannot carry 16 data lines plus strobe plus barcode. That is correct and we are not
asking for it to change.

Recorded here only because it constrains us in a way that was not obvious from outside:
**analysis in Intan's own timebase is blind to event identity until barcode alignment has
run**, and a real-time client on the Intan host cannot condition on event identity read from
that machine's digital inputs. Our neural plane must therefore learn trial state over the
message bus rather than off the wire. No change requested; noted so the constraint is written
down somewhere before someone assumes otherwise.
