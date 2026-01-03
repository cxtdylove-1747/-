"""
Environment fingerprint collection.

Goal: make reports more reproducible/credible without adding heavy dependencies.
We only use stdlib + best-effort subprocess calls (timeouts, ignore failures).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional


def _run(cmd: List[str], timeout: int = 2) -> str:
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return (p.stdout or "").strip()
    except Exception:
        return ""


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def collect_env_info(
    engines: Optional[List[str]] = None,
    cri_endpoints: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Collect a lightweight environment fingerprint.

    - engines: list like ["isulad","containerd","crio"]
    - cri_endpoints: map engine->endpoint for CRI engines (for crictl version probing)
    """
    engines = engines or []
    cri_endpoints = cri_endpoints or {}

    info: Dict[str, Any] = {
        "timestamp": int(time.time()),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "os_release": {},
        "hardware": {},
        "disk": {},
        "binaries": {},
        "engines": {},
    }

    # /etc/os-release (best-effort)
    try:
        if os.path.exists("/etc/os-release"):
            kv = {}
            with open("/etc/os-release", "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    kv[k] = v.strip().strip('"')
            info["os_release"] = kv
    except Exception:
        pass

    # Hardware summaries (best-effort)
    lscpu = _run(["lscpu"], timeout=2)
    if lscpu:
        info["hardware"]["lscpu"] = lscpu
    freeh = _run(["free", "-h"], timeout=2)
    if freeh:
        info["hardware"]["free_h"] = freeh
    uname = _run(["uname", "-a"], timeout=2)
    if uname:
        info["hardware"]["uname_a"] = uname

    # Disk (best-effort)
    dfh = _run(["df", "-h", "/"], timeout=2)
    if dfh:
        info["disk"]["df_root_h"] = dfh

    # Common binaries
    for b in ["isulad", "isula", "docker", "containerd", "ctr", "crictl", "crio", "runc", "podman"]:
        path = _which(b)
        if not path:
            continue
        info["binaries"][b] = {"path": path}
        # version probes (fast, best-effort)
        if b in ("docker", "podman", "crictl", "runc", "containerd", "crio"):
            out = _run([b, "--version"], timeout=2) or _run([b, "version"], timeout=2)
            if out:
                info["binaries"][b]["version"] = out
        if b == "isula":
            out = _run(["isula", "version"], timeout=2)
            if out:
                info["binaries"][b]["version"] = out
        if b == "isulad":
            out = _run(["isulad", "--version"], timeout=2) or _run(["isulad", "-v"], timeout=2)
            if out:
                info["binaries"][b]["version"] = out

    # Engine-specific best-effort probes
    for e in engines:
        e = str(e)
        info["engines"][e] = {}
        ep = cri_endpoints.get(e)
        if ep:
            info["engines"][e]["cri_endpoint"] = ep
            # Try to get runtime version via crictl against that endpoint
            if _which("crictl"):
                out = _run(["crictl", "-r", ep, "--timeout", "3s", "version"], timeout=4)
                if out:
                    info["engines"][e]["crictl_version"] = out

    return info


