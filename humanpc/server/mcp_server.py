"""MCP tool server — exposes humanpc verbs as agent-callable tools over stdio.

Each tool is a thin wrapper over the shared dispatcher, so an AI agent (Claude or
any MCP client) can drive the PC with the same semantics as the CLI/HTTP/Python
APIs. Lazy: the ``mcp`` package is only needed when you actually build/run it.
"""

from __future__ import annotations

from ..exceptions import DriverError


def build_server(bot=None):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:
        raise DriverError("MCP server needs the mcp package: pip install humanpc[server]") from exc

    from ..dispatch import execute

    if bot is None:
        from .. import Bot
        bot = Bot()

    server = FastMCP("humanpc")

    @server.tool()
    def click(target: str, button: str = "left", clicks: int = 1) -> dict:
        """Click a target (text, image path, or 'x,y')."""
        return execute(bot, "click", {"target": target, "button": button, "clicks": clicks})

    @server.tool()
    def type_text(text: str) -> dict:
        """Type text with human-like rhythm."""
        return execute(bot, "type", {"text": text})

    @server.tool()
    def press(keys: list[str]) -> dict:
        """Press keys in sequence (e.g. ['tab'])."""
        return execute(bot, "press", {"keys": keys})

    @server.tool()
    def hotkey(keys: list[str]) -> dict:
        """Press a chord (e.g. ['ctrl', 'c'])."""
        return execute(bot, "hotkey", {"keys": keys})

    @server.tool()
    def scroll(amount: int) -> dict:
        """Scroll by wheel clicks (negative = down)."""
        return execute(bot, "scroll", {"amount": amount})

    @server.tool()
    def find(target: str) -> dict:
        """Locate a target without acting; returns its match or none."""
        return execute(bot, "find", {"target": target})

    @server.tool()
    def wait_for(target: str, timeout: float = 10.0) -> dict:
        """Wait until a target appears."""
        return execute(bot, "wait_for", {"target": target, "timeout": timeout})

    @server.tool()
    def run(command: str) -> dict:
        """Run a shell command and capture output."""
        return execute(bot, "run", {"command": command})

    @server.tool()
    def open_app(target: str, wait: str | None = None) -> dict:
        """Launch an application."""
        return execute(bot, "open_app", {"target": target, "wait": wait})

    @server.tool()
    def list_windows() -> dict:
        """List open windows."""
        return execute(bot, "windows", {})

    @server.tool()
    def focus(title: str) -> dict:
        """Bring a window to the foreground by title."""
        return execute(bot, "focus", {"title": title})

    @server.tool()
    def read_text() -> dict:
        """OCR the screen and return recognised text."""
        return execute(bot, "read_text", {})

    return server


def main() -> None:
    build_server().run()
