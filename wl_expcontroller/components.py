"""Custom components: the typed seam S1 §8 settled on.

A task may name behaviour the vocabulary lacks. It may not *contain* it. The name
resolves to a component in this framework's own source -- typed, unit-tested,
reviewed like framework code, and versioned -- so the task file stays pure data and
the novelty lives where a human already looks.

S1's bake-off considered forbidding this outright, and the evidence supported it:
the residue that genuinely resists declaration is one narrow case, novel per-frame
computation. It was rejected because a novel paradigm blocking on framework work,
at exactly the moment the science wants to move, is what makes people fork the
framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Registry:
    """The components a task is permitted to name.

    Keyed by name, valued by the review record. A name absent from here is the
    seam being used as a hole.
    """

    reviewed: dict[str, str] = field(default_factory=dict)

    def __contains__(self, name: str) -> bool:
        return name in self.reviewed
