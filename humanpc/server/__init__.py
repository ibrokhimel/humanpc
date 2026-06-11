"""Server adapters (HTTP + MCP) over the shared dispatcher.

Both are lazy: importing this package pulls in neither fastapi nor mcp. Build the
one you need via ``build_app()`` / ``build_server()``.
"""

from __future__ import annotations

__all__ = ["build_app", "build_server"]


def build_app(bot=None):
    from .http import build_app as _build
    return _build(bot)


def build_server(bot=None):
    from .mcp_server import build_server as _build
    return _build(bot)
