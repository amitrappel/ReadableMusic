"""The steps of a conversion, for whoever waits on it: what it does now, and why now."""

from typing import NamedTuple


class Step(NamedTuple):
    """Passed to a conversion's log in place of a message; printed, it reads as what it does."""

    what: str
    why: str

    def __str__(self) -> str:
        return self.what
