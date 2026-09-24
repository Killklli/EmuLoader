"""Context, GUI, watcher loop and launcher entry point for the EmuLoader Archipelago client."""

from __future__ import annotations

import asyncio
import enum
import inspect
import shlex
from typing import Any, Callable, Dict, Optional

import Utils
from CommonClient import (
    ClientCommandProcessor,
    CommonContext,
    get_base_parser,
    gui_enabled,
    logger,
    server_loop,
)

from ..emulatorinfo import EmulatorInfo
from .discovery import DiscoveredHandler, connect_and_identify, discover_handlers, revalidate


class AuthStatus(enum.IntEnum):
    NOT_AUTHENTICATED = 0
    NEED_INFO = 1
    PENDING = 2
    AUTHENTICATED = 3


class EmuLoaderCommandProcessor(ClientCommandProcessor):
    def _cmd_emu(self):
        """Show the current emulator/device connection status."""
        assert isinstance(self.ctx, EmuLoaderClientContext)
        if self.ctx.client_handler is None:
            logger.info("Status: Not connected")
        elif self.ctx.transport_mode == "alternate":
            logger.info(f"Status: Connected to {self.ctx.current_game} (alternate transport)")
        else:
            name = self.ctx.emulator_info.readable_emulator_name if self.ctx.emulator_info else "?"
            logger.info(f"Status: Connected to {self.ctx.current_game} ({name})")

    # ------------------------------------------------------------------ #
    # Handler-contributed commands
    # ------------------------------------------------------------------ #
    def _handler_commands(self) -> Dict[str, Callable]:
        """The active handler's ``client_commands`` mapping (name -> callable(ctx, *args))."""
        handler = getattr(self.ctx, "client_handler", None)
        cmds = getattr(handler, "client_commands", None)
        return cmds if isinstance(cmds, dict) else {}

    def __call__(self, raw: str):
        # Intercept slash commands the built-in set doesn't know, and offer them to the active
        # handler's client_commands before falling back to the default "unknown command" path.
        if raw and raw[0] == self.marker:
            try:
                parts = shlex.split(raw, comments=False)
            except ValueError:
                parts = raw.split()
            if parts:
                name = parts[0][1:].lower()
                if name not in self.commands:
                    func = self._handler_commands().get(name)
                    if func is not None:
                        try:
                            if getattr(func, "raw_text", False):
                                rest = raw.split(maxsplit=1)
                                result = func(self.ctx, rest[1]) if len(rest) > 1 else func(self.ctx)
                            else:
                                result = func(self.ctx, *parts[1:])
                            if inspect.iscoroutine(result):
                                Utils.async_start(result)
                                return None
                            return result
                        except Exception as exc:  # noqa: BLE001 - mirror base error handling
                            self._error_parsing_command(exc)
                            return None
        return super().__call__(raw)

    def get_help_text(self) -> str:
        text = super().get_help_text()
        for name, func in self._handler_commands().items():
            doc = (inspect.getdoc(func) or "(missing help text)").replace("\n", "\n    ")
            text += f"{self.marker}{name}\n    {doc}\n"
        return text


class EmuLoaderClientContext(CommonContext):
    command_processor = EmuLoaderCommandProcessor
    items_handling = None  # set by the discovered handler on connection

    emulator_info: Optional[EmulatorInfo]
    client_handler: Optional[object]
    current_game: Optional[str]
    transport_mode: Optional[str]  # "emulator" | "alternate" | None
    auth_status: AuthStatus
    password_requested: bool
    slot_data: Optional[dict[str, Any]]
    watcher_timeout: float
    pull_from_web: bool

    def __init__(self, server_address: Optional[str], password: Optional[str],
                 pull_from_web: bool = True) -> None:
        super().__init__(server_address, password)
        self.emulator_info = None
        self.client_handler = None
        self.current_game = None
        self.transport_mode = None
        self.active_validation = None
        self.auth_status = AuthStatus.NOT_AUTHENTICATED
        self.password_requested = False
        self.slot_data = None
        self.watcher_timeout = 0.5
        self.pull_from_web = pull_from_web
        self._not_connected_logged = False


    def _emu_ready(self) -> bool:
        if self.emulator_info is None:
            if self.transport_mode != "alternate" and not self._not_connected_logged:
                logger.warning("Not connected to emulator.")
                self._not_connected_logged = True
            return False
        return True

    def read_u8(self, address: int) -> int:
        return self.emulator_info.read_u8(address) if self._emu_ready() else 0

    def read_u16(self, address: int) -> int:
        return self.emulator_info.read_u16(address) if self._emu_ready() else 0

    def read_u32(self, address: int) -> int:
        return self.emulator_info.read_u32(address) if self._emu_ready() else 0

    def write_u8(self, address: int, value: int) -> None:
        if self._emu_ready():
            self.emulator_info.write_u8(address, value)

    def write_u16(self, address: int, value: int) -> None:
        if self._emu_ready():
            self.emulator_info.write_u16(address, value)

    def write_u32(self, address: int, value: int) -> None:
        if self._emu_ready():
            self.emulator_info.write_u32(address, value)

    def read_bytestring(self, address: int, length: int) -> str:
        return self.emulator_info.read_bytestring(address, length) if self._emu_ready() else ""

    def write_bytestring(self, address: int, data: str) -> None:
        if self._emu_ready():
            self.emulator_info.write_bytestring(address, data)

    def _reset_connection(self) -> None:
        """Tear down whatever transport is active (emulator or handler-owned) and clear state."""
        handler = self.client_handler
        if handler is not None:
            disconnect = getattr(handler, "alternate_disconnect", None)
            if callable(disconnect):
                try:
                    disconnect(self)
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass
        if self.emulator_info is not None:
            self.emulator_info.disconnect()
        self.emulator_info = None
        self.client_handler = None
        self.current_game = None
        self.transport_mode = None
        self.active_validation = None
        self._not_connected_logged = False

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = "Archipelago EmuLoader Client"
        return ui

    def on_package(self, cmd: str, args: dict) -> None:
        if cmd == "Connected":
            self.slot_data = args.get("slot_data", None)
            self.auth_status = AuthStatus.AUTHENTICATED

        handler = self.client_handler
        on_package = getattr(handler, "on_package", None)
        if callable(on_package):
            on_package(self, cmd, args)

    def on_print_json(self, args: dict) -> None:
        super().on_print_json(args)
        handler = self.client_handler
        on_print_json = getattr(handler, "on_print_json", None)
        if callable(on_print_json):
            on_print_json(self, args)

    def on_deathlink(self, data: dict) -> None:
        super().on_deathlink(data)
        handler = self.client_handler
        on_deathlink = getattr(handler, "on_deathlink", None)
        if callable(on_deathlink):
            on_deathlink(self, data)

    async def server_auth(self, password_requested: bool = False) -> None:
        self.password_requested = password_requested

        if self.client_handler is None:
            logger.info("Awaiting connection to an emulator or device before authenticating.")
            return

        if self.auth is None:
            self.auth_status = AuthStatus.NEED_INFO
            set_auth = getattr(self.client_handler, "set_auth", None)
            if callable(set_auth):
                await set_auth(self)
            if self.auth is None:
                # A handler may decline the username prompt (e.g. it reads the slot name from a
                # hardware bridge) by returning False from wants_username_prompt(ctx). In that
                # case it is responsible for setting ctx.auth and re-invoking server_auth later.
                wants_prompt = getattr(self.client_handler, "wants_username_prompt", None)
                if callable(wants_prompt):
                    wants_prompt = wants_prompt(self)
                if wants_prompt is None or wants_prompt:
                    await self.get_username()
                else:
                    return

        if password_requested and not self.password:
            self.auth_status = AuthStatus.NEED_INFO
            await super().server_auth(password_requested)

        await self.send_connect()
        self.auth_status = AuthStatus.PENDING

    async def disconnect(self, allow_autoreconnect: bool = False) -> None:
        self.auth_status = AuthStatus.NOT_AUTHENTICATED
        await super().disconnect(allow_autoreconnect)


def _adopt_handler(ctx: EmuLoaderClientContext, emu: EmulatorInfo, discovered: DiscoveredHandler) -> None:
    """Wire a freshly identified emulator + handler into the context (process-memory transport)."""
    ctx.emulator_info = emu
    ctx.client_handler = discovered.handler
    ctx.current_game = discovered.game
    ctx.active_validation = discovered.validation
    ctx.game = discovered.game
    ctx.items_handling = getattr(discovered.handler, "items_handling", 0b001)
    ctx.transport_mode = "emulator"
    ctx._not_connected_logged = False


def _adopt_alternate(ctx: EmuLoaderClientContext, discovered: DiscoveredHandler) -> None:
    """Wire a handler that connected via its own transport (e.g. EverDrive 64 socket bridge)."""
    ctx.emulator_info = None
    ctx.client_handler = discovered.handler
    ctx.current_game = discovered.game
    ctx.active_validation = discovered.validation
    ctx.game = discovered.game
    ctx.items_handling = getattr(discovered.handler, "items_handling", 0b001)
    ctx.transport_mode = "alternate"
    ctx._not_connected_logged = False


async def _drop_connection(ctx: EmuLoaderClientContext) -> None:
    """Reset the transport and, if a server is connected, drop and let it reauthenticate."""
    ctx._reset_connection()
    if ctx.server is not None and not ctx.server.socket.closed:
        ctx.auth = None
        ctx.username = None
        ctx.finished_game = False
        await ctx.disconnect(False)


async def _game_watcher(ctx: EmuLoaderClientContext) -> None:
    showed_connecting_message = False
    showed_no_handler_message = False
    loop = asyncio.get_event_loop()

    while not ctx.exit_event.is_set():
        try:
            await asyncio.wait_for(ctx.watcher_event.wait(), ctx.watcher_timeout)
        except asyncio.TimeoutError:
            pass
        ctx.watcher_event.clear()

        try:
            if ctx.client_handler is None:
                handlers = discover_handlers()
                if not handlers:
                    if not showed_no_handler_message:
                        logger.info("No EmuLoader-compatible worlds are installed. Install a supported "
                                    "N64 apworld, then restart the client.")
                        showed_no_handler_message = True
                    continue
                showed_no_handler_message = False

                if not showed_connecting_message:
                    logger.info("Waiting to connect to a supported emulator or device...")
                    showed_connecting_message = True

                # 1) Try emulator (process-memory) detection. Blocking scan -> run off the loop,
                #    and let exit cancel the wait.
                connect_task = loop.run_in_executor(None, connect_and_identify, handlers, ctx.pull_from_web)
                exit_task = asyncio.create_task(ctx.exit_event.wait(), name="ExitWait")
                await asyncio.wait({connect_task, exit_task}, return_when=asyncio.FIRST_COMPLETED)
                if exit_task.done():
                    return
                exit_task.cancel()
                result = connect_task.result()

                if result is not None:
                    emu, discovered = result
                    _adopt_handler(ctx, emu, discovered)
                    showed_connecting_message = False
                    logger.info(f"Running handler for {discovered.game} ({emu.readable_emulator_name})")

                    validate_rom = getattr(discovered.handler, "validate_rom", None)
                    if callable(validate_rom) and not await validate_rom(ctx):
                        logger.info(f"{discovered.game} is not ready yet; waiting...")
                        ctx._reset_connection()
                        continue
                else:
                    # 2) No emulator found: offer each handler its own transport
                    adopted = False
                    for discovered in handlers.values():
                        alternate_connect = getattr(discovered.handler, "alternate_connect", None)
                        if not callable(alternate_connect):
                            continue
                        try:
                            if await alternate_connect(ctx):
                                _adopt_alternate(ctx, discovered)
                                showed_connecting_message = False
                                logger.info(f"Running handler for {discovered.game} (alternate transport)")
                                adopted = True
                                break
                        except Exception as exc:  # noqa: BLE001 - try the next handler
                            logger.debug(f"alternate_connect failed for {discovered.game}: {exc}")
                    if not adopted:
                        continue
            else:
                # Connected — verify the active transport is still alive.
                if ctx.transport_mode == "emulator":
                    if not await loop.run_in_executor(None, revalidate, ctx.emulator_info, ctx.active_validation):
                        logger.info("Lost connection to emulator (closed or ROM changed). Reconnecting...")
                        await _drop_connection(ctx)
                        continue
                else:  # alternate transport
                    alive = getattr(ctx.client_handler, "alternate_connected", None)
                    if callable(alive) and not await alive(ctx):
                        logger.info("Lost connection to device. Reconnecting...")
                        await _drop_connection(ctx)
                        continue
        except Exception as exc:  # noqa: BLE001 - never let the watcher die
            logger.exception(exc)
            ctx._reset_connection()
            continue

        # Server auth once an emulator/device + handler is known.
        if ctx.server is not None and not ctx.server.socket.closed:
            if ctx.auth_status == AuthStatus.NOT_AUTHENTICATED:
                Utils.async_start(ctx.server_auth(ctx.password_requested))
        else:
            ctx.auth_status = AuthStatus.NOT_AUTHENTICATED

        try:
            await ctx.client_handler.game_watcher(ctx)
        except Exception as exc:  # noqa: BLE001 - a handler error shouldn't kill the client
            logger.exception(exc)
            ctx._reset_connection()


def launch(*launch_args: str) -> None:
    async def main():
        parser = get_base_parser()
        parser.add_argument("--no-pull-from-web", action="store_true",
                            help="Use only the bundled emulator config instead of fetching the latest from the web.")
        args = parser.parse_args(launch_args)

        ctx = EmuLoaderClientContext(args.connect, args.password, pull_from_web=not args.no_pull_from_web)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")

        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()

        watcher_task = asyncio.create_task(_game_watcher(ctx), name="GameWatcher")
        try:
            await watcher_task
        except Exception as exc:  # noqa: BLE001
            logger.exception(exc)

        await ctx.exit_event.wait()
        await ctx.shutdown()

    Utils.init_logging("EmuLoaderClient", exception_logger="Client")
    import colorama

    colorama.just_fix_windows_console()
    asyncio.run(main())
    colorama.deinit()
