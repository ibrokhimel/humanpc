"""FastAPI HTTP server exposing every verb as ``POST /<action>``.

Lazy: importing this module is cheap; FastAPI is only required when you actually
build the app. The route handler is a one-liner over the shared dispatcher.
"""

from __future__ import annotations

from ..exceptions import DriverError


def build_app(bot=None):
    try:
        from fastapi import Body, FastAPI, HTTPException
    except Exception as exc:
        raise DriverError("HTTP server needs fastapi: pip install humanpc[server]") from exc

    from ..dispatch import execute, list_actions

    if bot is None:
        from .. import Bot
        bot = Bot()

    app = FastAPI(title="humanpc", version="0.0.1")

    @app.get("/actions")
    def actions():
        return {"actions": list_actions()}

    @app.post("/{action}")
    def do(action: str, params: dict = Body(default={})):
        try:
            return execute(bot, action, params)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # surface backend/target errors as 422
            raise HTTPException(status_code=422, detail=str(exc))

    return app


def main(host: str = "127.0.0.1", port: int = 8000, **bot_kwargs) -> None:
    import uvicorn

    from .. import Bot

    uvicorn.run(build_app(Bot(**bot_kwargs)), host=host, port=port)
