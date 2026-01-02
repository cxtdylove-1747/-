"""iSulad engine.

This project supports running CRI benchmarks via ``executor/cri_executor.py`` using
``crictl``. Engines therefore act as *CRI endpoint providers* rather than full
CRI API client implementations.

The engine's responsibility is to validate and return the CRI endpoint (usually
a Unix domain socket path). Any CRI operations are executed by the CRI executor
and are intentionally not implemented here.
"""

from __future__ import annotations

import os
from typing import Any

from .base import Engine


class ISulad(Engine):
    """Provide the CRI endpoint for iSulad."""

    name = "isulad"
    # common default for iSulad
    cri_socket = "/var/run/isulad.sock"

    def connect(self, endpoint: str | None = None, **_: Any) -> str:
        """Validate and return the CRI endpoint.

        Parameters
        ----------
        endpoint:
            Optional override for the CRI socket path.

        Returns
        -------
        str
            The validated endpoint.
        """
        ep = endpoint or self.cri_socket
        if ep.startswith("unix://"):
            path = ep[len("unix://") :]
        else:
            path = ep

        if not os.path.exists(path):
            raise FileNotFoundError(f"CRI socket not found: {path}")
        return ep

    # ---- CRI operations are executed via crictl in executor/cri_executor.py ----
    def run(self, *args: Any, **kwargs: Any):  # type: ignore[override]
        raise NotImplementedError("CRI operations are executed by cri_executor via crictl")

    def stop(self, *args: Any, **kwargs: Any):  # type: ignore[override]
        raise NotImplementedError("CRI operations are executed by cri_executor via crictl")

    def status(self, *args: Any, **kwargs: Any):  # type: ignore[override]
        raise NotImplementedError("CRI operations are executed by cri_executor via crictl")
