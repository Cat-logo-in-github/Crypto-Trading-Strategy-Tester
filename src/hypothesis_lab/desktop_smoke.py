"""Offline acceptance check for the portable desktop runtime and local service."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from . import __version__
from .data import fixtures
from .research import run_experiment
from .server import LocalServer


def run_smoke(temporary_parent: Path | None = None) -> dict:
    portable = os.environ.get("HYPOTHESIS_LAB_PORTABLE") == "1"
    app_file = Path(__file__).resolve()
    if portable:
        app_root = Path(sys.executable).resolve().parent.parent
        if not app_file.is_relative_to(app_root / "hypothesis_lab"):
            raise AssertionError("Application was imported outside the portable folder")
        if not sys.flags.isolated or not sys.flags.no_site:
            raise AssertionError("Portable runtime must ignore installed Python packages")
        if any(not Path(item).resolve().is_relative_to(app_root) for item in sys.path):
            raise AssertionError("Portable Python search path escaped the application folder")
    bars, events = fixtures()
    if len(bars) < 200 or not events:
        raise AssertionError("Bundled market/weather fixtures are missing")
    model = run_experiment({"mode": "ml"}, persist=False)
    if model.get("mode") != "ml" or "summary" not in model:
        raise AssertionError("Offline model workflow did not complete")
    previous_state = os.environ.get("HYPOTHESIS_LAB_HOME")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    if temporary_parent is None and os.environ.get("HYPOTHESIS_LAB_SMOKE_HOME"):
        temporary_parent = Path(os.environ["HYPOTHESIS_LAB_SMOKE_HOME"])
    if temporary_parent is not None:
        temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="hypothesis-lab-desktop-", dir=temporary_parent
    ) as state:
        os.environ["HYPOTHESIS_LAB_HOME"] = state
        server = LocalServer(0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        try:
            with opener.open(origin, timeout=10) as response:
                page = response.read()
            if b"Hypothesis" not in page:
                raise AssertionError("Local interface was not served")
            with opener.open(origin + "/app.js", timeout=10) as response:
                if len(response.read()) < 100:
                    raise AssertionError("Local interface script is missing")
            with opener.open(origin + "/api/bootstrap", timeout=10) as response:
                bootstrap = json.load(response)
            token = bootstrap.get("token")
            if not isinstance(token, str) or len(token) < 20:
                raise AssertionError("Local session token was not provided")
            request = urllib.request.Request(
                origin + "/api/run",
                data=b'{"mode":"rules","persist_local":false}',
                headers={
                    "Content-Type": "application/json",
                    "Origin": origin,
                    "X-Lab-Token": token,
                },
            )
            with opener.open(request, timeout=20) as response:
                experiment = json.load(response)
            if "summary" not in experiment:
                raise AssertionError("HTTP experiment workflow did not complete")
            request = urllib.request.Request(
                origin + "/api/shutdown",
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "Origin": origin,
                    "X-Lab-Token": token,
                },
            )
            with opener.open(request, timeout=10) as response:
                if json.load(response).get("status") != "stopping":
                    raise AssertionError("Authenticated shutdown was not acknowledged")
            worker.join(timeout=5)
            if worker.is_alive():
                raise AssertionError("Local service did not shut down")
            if list(Path(state).rglob("*.json")):
                raise AssertionError("Session-only checks unexpectedly saved user state")
        finally:
            if worker.is_alive():
                server.shutdown()
                worker.join(timeout=5)
            server.server_close()
            if previous_state is None:
                os.environ.pop("HYPOTHESIS_LAB_HOME", None)
            else:
                os.environ["HYPOTHESIS_LAB_HOME"] = previous_state
    return {
        "status": "passed",
        "version": __version__,
        "portable": portable,
        "python": sys.version.split()[0],
        "application": str(app_file),
        "checks": [
            "bundled fixtures",
            "offline model",
            "HTTP interface",
            "HTTP session",
            "HTTP experiment",
            "authenticated shutdown",
            "no saved research state",
        ],
    }


def main() -> None:
    print(json.dumps(run_smoke(), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
