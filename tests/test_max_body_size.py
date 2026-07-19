"""Guard for the aiohttp client_max_size bump (image requests exceed default 1MB).

The upstream endpoint uses bare web.Application() → aiohttp default client_max_size
= 1MB. A base64 image + long conversation history blows past it, request.json()
raises, and the author handler returns 400 "invalid JSON" (observed 2026-07-19 on
image drag). _patch_max_body_size raises the default so image requests parse.
"""
import laap.chatflow as cf


def _fresh_app_init():
    """Save/restore web.Application.__init__ so the global patch doesn't leak."""
    from aiohttp import web
    return web, web.Application.__init__


def test_bumps_default_client_max_size():
    web, orig = _fresh_app_init()
    web.Application.__init__ = getattr(orig, "__wrapped_orig__", orig)  # reset if wrapped
    try:
        # force a clean unpatched state
        web.Application.__init__ = orig
        cf._patch_max_body_size()
        app = web.Application()
        assert app._client_max_size == cf._MAX_BODY
        assert cf._MAX_BODY >= 8 * 1024 * 1024   # comfortably above 1MB for images
    finally:
        web.Application.__init__ = orig


def test_respects_explicit_size():
    web, orig = _fresh_app_init()
    try:
        web.Application.__init__ = orig
        cf._patch_max_body_size()
        app = web.Application(client_max_size=5 * 1024 * 1024)
        assert app._client_max_size == 5 * 1024 * 1024   # caller's choice wins
    finally:
        web.Application.__init__ = orig


def test_idempotent():
    web, orig = _fresh_app_init()
    try:
        web.Application.__init__ = orig
        cf._patch_max_body_size()
        once = web.Application.__init__
        cf._patch_max_body_size()          # second call is a no-op
        assert web.Application.__init__ is once
    finally:
        web.Application.__init__ = orig
