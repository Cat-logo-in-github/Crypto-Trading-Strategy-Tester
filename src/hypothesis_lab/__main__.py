"""Documented launcher and offline research commands."""

from __future__ import annotations

import argparse
import json
import webbrowser
from pathlib import Path

from .research import run_experiment
from .server import make_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Hypothesis Lab: local, reproducible research")
    parser.add_argument("command", nargs="?", choices=["serve", "sample", "ml"], default="serve")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command != "serve":
        result = run_experiment({"mode": "ml" if args.command == "ml" else "rules"}, persist=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        print(
            json.dumps(
                {
                    "id": result["id"],
                    "dataset": result["dataset"]["source"],
                    "summary": result["summary"],
                },
                indent=2,
            )
        )
        return
    try:
        server = make_server(args.port)
    except OSError:
        parser.exit(1, "The local port is unavailable. Try --port 8766.\n")
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Hypothesis Lab is running at {url}\nStop with Ctrl+C or the Stop app button.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("Hypothesis Lab stopped.")


if __name__ == "__main__":
    main()
