"""Deprecated alias decorator for the v0.6.0 accessor reorganisation.

This module provides the :func:`deprecated_alias` decorator factory used
across all v0.6.0 accessor migration phases (21-24).  Each flat ``db.*``
stub is decorated with ``@deprecated_alias("accessor.method")`` so that
the implementation lives in the accessor while the old call-path still
works — with a :class:`DeprecationWarning` — until v0.7.0.
"""

from __future__ import annotations

import functools
import inspect
import warnings


def deprecated_alias(target_path: str):
    """Decorate a flat stub to warn and delegate to an accessor method.

    Parameters
    ----------
    target_path : str
        Dotted path of the form ``"<accessor>.<method>"`` — e.g.
        ``"timescale.create_hypertable"``.  Resolved lazily on ``self``
        at call time so no hard reference is needed at decoration time.

    Returns
    -------
    Callable
        A decorator that replaces the stub with warn-then-delegate logic.
        The wrapper is ``async def`` when the stub is a coroutine function,
        ``def`` otherwise.
    """

    def decorator(fn):
        """Apply warn-then-delegate wrapping to the stub function ``fn``."""
        msg = (
            f"use `db.{target_path}` instead; "
            f"the flat `db.{fn.__name__}` alias is deprecated "
            "and will be removed in v0.7.0"
        )
        accessor_name, method_name = target_path.split(".", 1)

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(self, *args, **kwargs):
                """Emit DeprecationWarning then await the accessor coroutine."""
                warnings.warn(msg, DeprecationWarning, stacklevel=2)
                accessor = getattr(self, accessor_name)
                return await getattr(accessor, method_name)(*args, **kwargs)

            return async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(self, *args, **kwargs):
                """Emit DeprecationWarning then call the accessor method."""
                warnings.warn(msg, DeprecationWarning, stacklevel=2)
                accessor = getattr(self, accessor_name)
                return getattr(accessor, method_name)(*args, **kwargs)

            return sync_wrapper

    return decorator
