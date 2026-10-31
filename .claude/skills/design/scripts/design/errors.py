"""The failures a unit raises when a command ran but cannot produce its result, each carrying the exit code the CLI turns it into."""

from __future__ import annotations


class Failure(Exception):
    """Exit 1. `message` is what went wrong in terms the caller can act on; `detail` rides along in the JSON."""

    code = 1

    def __init__(self, message: str, **detail):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def payload(self) -> dict:
        return {"error": self.message, **self.detail}


class Usage(Failure):
    """Exit 2: the arguments cannot work, found only once the ledger or the data folder was read."""

    code = 2


class Unavailable(Failure):
    """Exit 3: the environment cannot run this (an ArtCraft CLI or app, codex, macOS Vision, the network)."""

    code = 3


class BadInput(Failure):
    """Exit 4: an input file could not be read."""

    code = 4


class Conflict(Failure):
    """Exit 5: going on would lose 성진's work (the document is open in an app, or holds changes no version has)."""

    code = 5
