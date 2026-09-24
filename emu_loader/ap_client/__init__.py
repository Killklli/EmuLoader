"""EmuLoader Archipelago client package."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .context import EmuLoaderClientContext


@runtime_checkable
class EmuLoaderClientHandler(Protocol):
    """The duck-typed contract a world's ``n64_client_handler`` should satisfy.

    Only :meth:`game_watcher` is required. Memory access is done through ``ctx`` (``ctx.read_u8``,
    ``ctx.write_u8``, ``ctx.read_bytestring``, ...), so a handler needs no EmuLoader import.
    """

    items_handling: int

    async def game_watcher(self, ctx: "EmuLoaderClientContext") -> None:
        """Run one tick of per-game logic: read state, check locations, give items, set goal.

        Called repeatedly (roughly every ``ctx.watcher_timeout`` seconds) once the correct ROM is
        confirmed loaded and the emulator is connected.
        """


def launch(*args: str) -> None:
    """Launch the EmuLoader client. Lazily imports the AP/Kivy-coupled context module."""
    from .context import launch as _launch
    _launch(*args)


__all__ = ["EmuLoaderClientHandler", "launch"]
