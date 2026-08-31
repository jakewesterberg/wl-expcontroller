# Reference tasks

**The task library belongs to `wl-mllib`** (ADR-0007). These live here until it has
one, for the same reason `codes.py` carries a provisional allocation: something has
to exercise the checker, the runner and the review artifact before the repository
that will own them is written.

They are the two tasks S1's bake-off argued over, now as real files rather than
snippets in a spec. `tests/test_reference_tasks.py` asserts each one passes every
load-time check and that simulation reaches every outcome it declares -- which is
the acceptance test ADR-0006 rests on, applied to the tasks that demonstrate it.
