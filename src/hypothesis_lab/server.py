"""Loopback-only local UI. Token, same-origin and Host checks protect mutations."""

from __future__ import annotations

import importlib.util
import json
import mimetypes
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .algorithms import FUNCTIONS, plan_algorithm, plan_with_llm
from .features import demo_content, idea_examples, inspect_dataset, market_from_dataset
from .ideas import plan_idea
from .models import inspect_uploaded
from .providers import alpha_vantage_test, kraken_snapshot, open_meteo
from .research import events_csv, feature_search, rerun_payload, run_experiment
from .sources import catalog, fetch_source, search_sources
from .storage import (
    credential_status,
    list_experiments,
    load_credential,
    load_experiment,
    remove_credential,
    save_credential,
)
from .strategies import parse_hypothesis, preset


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int = 8765):
        super().__init__(("127.0.0.1", port), Handler)
        self.token = secrets.token_urlsafe(32)
        self.run_lock = threading.Lock()
        self.provider_lock = threading.Lock()
        self.last_refresh: dict[str, float] = {}
        self.session_runs: dict[str, dict] = {}

    def remember(self, value: dict) -> dict:
        self.session_runs[value["id"]] = value
        while (
            len(self.session_runs) > 20
            or sum(len(json.dumps(record)) for record in self.session_runs.values()) > 50_000_000
        ):
            if len(self.session_runs) <= 1:
                break
            self.session_runs.pop(next(iter(self.session_runs)))
        return value

    def experiment(self, identity: str) -> dict:
        return (
            self.session_runs[identity]
            if identity in self.session_runs
            else load_experiment(identity)
        )


class Handler(BaseHTTPRequestHandler):
    server: LocalServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format: str, *args) -> None:
        # Request URLs/bodies may contain research data. No access logs.
        pass

    def _host_valid(self) -> bool:
        return self.headers.get("Host") in {
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        }

    def _send(self, code: int, value, kind: str = "application/json; charset=utf-8") -> None:
        if code >= 400 and self.command == "POST" and not getattr(self, "_body_read", False):
            # A bounded drain of already-sent rejected input avoids Windows resetting
            # the connection before a small error response reaches the client.
            # Never trust an invalid/oversized Content-Length or wait for its full body.
            timeout = self.connection.gettimeout()
            try:
                self.connection.settimeout(0.05)
                self.rfile.read1(65536)
            except OSError:
                pass
            finally:
                self.connection.settimeout(timeout)
        raw = (
            json.dumps(value, allow_nan=False).encode()
            if kind.startswith("application/json")
            else value
        )
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if not self._host_valid():
            self._send(403, {"error": "Only local application hosts are accepted"})
            return
        path = urlsplit(self.path).path
        try:
            if path == "/api/bootstrap":
                # Cross-origin pages cannot read this response (no CORS headers).
                self._send(
                    200,
                    {
                        "token": self.server.token,
                        "version": __version__,
                        "preset": preset("buy_hold"),
                        "settings": credential_status(),
                        "feature_demo": demo_content(),
                        "idea_examples": idea_examples(),
                        "algorithm_functions": FUNCTIONS,
                        "project": "Student project for historical strategy research and simulated paper trading. No real orders or promise of profitable/scientifically conclusive results.",
                        "privacy": "Experiments and source/model keys are session-only by default. Export or explicitly save locally when you choose; there is no app-operator backend.",
                        "optional_models": {
                            "onnx": importlib.util.find_spec("onnxruntime") is not None,
                            "endpoint": True,
                            "portable": os.environ.get("HYPOTHESIS_LAB_PORTABLE") == "1",
                        },
                    },
                )
            elif path == "/api/history":
                records = [
                    {
                        k: value.get(k)
                        for k in ("id", "created_at", "mode", "name", "dataset", "summary")
                    }
                    for value in reversed(list(self.server.session_runs.values()))
                ]
                if parse_qs(urlsplit(self.path).query).get("include_saved") == ["1"]:
                    seen = {value["id"] for value in records}
                    records.extend(value for value in list_experiments() if value["id"] not in seen)
                self._send(200, records)
            elif path == "/api/sources/catalog":
                self._send(200, {"sources": catalog()})
            elif path.startswith("/api/experiments/"):
                if self.headers.get("X-Lab-Token") != self.server.token:
                    self._send(403, {"error": "Open the local application to export experiments"})
                    return
                self._send(200, self.server.experiment(path.rsplit("/", 1)[-1]))
            elif path == "/api/public-results":
                self._send(
                    200,
                    json.loads(
                        (
                            Path(__file__).with_name("fixtures") / "public-strategy-results.json"
                        ).read_text(encoding="utf-8")
                    ),
                )
            elif path == "/api/scenarios":
                from .scenarios import catalogue, scenario_payload

                identity = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
                self._send(
                    200,
                    {
                        "scenario": next((x for x in catalogue() if x["id"] == identity), None),
                        "payload": scenario_payload(identity),
                    }
                    if identity
                    else {"scenarios": catalogue()},
                )
            elif path == "/api/portfolio/templates":
                from .portfolio_templates import catalogue, template_payload

                identity = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
                self._send(
                    200,
                    {
                        "template": next((x for x in catalogue() if x["id"] == identity), None),
                        "payload": template_payload(identity),
                    }
                    if identity
                    else {"templates": catalogue()},
                )
            elif path == "/api/execution/profiles":
                from .costs import execution_profiles

                self._send(200, {"profiles": execution_profiles()})
            elif path in {
                "/",
                "/app.js",
                "/style.css",
                "/workbench.js",
                "/terminal.css",
                "/studio.js",
                "/studio.css",
                "/favicon.svg",
                "/lab.js",
                "/lab.css",
                "/portfolio-ui.js",
                "/portfolio-ui.css",
            }:
                name = "index.html" if path == "/" else path[1:]
                file = Path(__file__).with_name("static") / name
                self._send(
                    200,
                    file.read_bytes(),
                    mimetypes.guess_type(name)[0] or "application/octet-stream",
                )
            else:
                self._send(404, {"error": "Not found"})
        except (OSError, ValueError):
            self._send(404, {"error": "Saved experiment or asset was not found"})

    def do_POST(self) -> None:
        port = self.server.server_port
        origin = self.headers.get("Origin")
        if (
            not self._host_valid()
            or origin not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
            or self.headers.get("X-Lab-Token") != self.server.token
        ):
            self._send(403, {"error": "Local session validation failed; reload the application"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            path = urlsplit(self.path).path
            limit = (
                12_000_000
                if path
                in {
                    "/api/run",
                    "/api/import",
                    "/api/model/inspect",
                    "/api/compute",
                    "/api/dataset/inspect",
                    "/api/dataset/market",
                    "/api/algorithm/preview",
                }
                else 3_000_000
            )
            if (
                not 0 < size <= limit
                or self.headers.get("Content-Type", "").split(";")[0] != "application/json"
            ):
                self._send(413, {"error": f"Send JSON of at most {limit // 1_000_000} MB"})
                return
            body = self.rfile.read(size)
            self._body_read = True
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("Request must be a JSON object")
            path = urlsplit(self.path).path
            if path in {
                "/api/run",
                "/api/search",
                "/api/import",
                "/api/rerun",
                "/api/algorithm/preview",
                "/api/scenarios/run",
            }:
                if not self.server.run_lock.acquire(blocking=False):
                    self._send(409, {"error": "An experiment is already running"})
                    return
                try:
                    if path == "/api/scenarios/run":
                        from .scenarios import run_scenarios

                        identity = payload.get("id")
                        value = run_scenarios(
                            [identity] if identity else None,
                            include_controls=payload.get("include_controls") is not False,
                            include_records=payload.get("include_records") is True,
                        )
                    elif path == "/api/algorithm/preview":
                        preview = run_experiment({**payload, "mode": "algorithm"}, persist=False)
                        value = {
                            "preview": preview["diagnostics"]["inference_decisions"][:20],
                            "interpretation": preview["algorithm"],
                            "period": preview["period"],
                            "warnings": preview["warnings"],
                            "fields": preview.get("feature_dataset", {}).get("generated_fields", [])
                            if preview.get("feature_dataset")
                            else [],
                        }
                    elif path == "/api/search":
                        value = feature_search(payload)
                    elif path == "/api/import":
                        value = self.server.remember(
                            run_experiment(
                                rerun_payload(payload), persist=payload.get("persist_local") is True
                            )
                        )
                    elif path == "/api/rerun":
                        rerun = rerun_payload(self.server.experiment(payload["id"]))
                        if payload.get("model_credential"):
                            rerun["model_credential"] = payload["model_credential"]
                        value = self.server.remember(
                            run_experiment(
                                rerun,
                                persist=payload.get("persist_local") is True,
                            )
                        )
                    else:
                        value = self.server.remember(
                            run_experiment(payload, persist=payload.get("persist_local") is True)
                        )
                finally:
                    self.server.run_lock.release()
            elif path == "/api/parse":
                value = parse_hypothesis(payload.get("text", ""), payload.get("fields"))
            elif path == "/api/algorithm/plan":
                description = payload.get("description", payload.get("query", ""))
                if not isinstance(description, str):
                    raise ValueError("Describe the algorithm using text")
                fields = payload.get("fields", [])
                value = (
                    plan_with_llm(
                        description, fields, payload["connection"], payload.get("credential")
                    )
                    if payload.get("connection")
                    else plan_algorithm(description, fields)
                )
                data_plan = plan_idea(description, fields)
                value["search_terms"] = data_plan["search_terms"]
                value["data_requirements"] = data_plan["data_requirements"]
            elif path == "/api/dataset/inspect":
                value = inspect_dataset(
                    payload.get("content", ""), payload.get("format", "csv"), payload.get("mapping")
                )
            elif path == "/api/dataset/market":
                value = market_from_dataset(
                    payload.get("content", ""),
                    payload.get("format", "csv"),
                    payload.get("mapping", {}),
                )
            elif path == "/api/model/inspect":
                value = inspect_uploaded(payload.get("artifact", payload))
            elif path == "/api/ideas/plan":
                value = plan_idea(payload.get("query", ""), payload.get("fields", []))
                if payload.get("connection"):
                    from .local_inference import llm_plan

                    value["llm_plan"] = llm_plan(
                        payload.get("query", ""), payload["connection"], payload.get("credential")
                    )
                    value["search_terms"] = value["llm_plan"]["search_terms"]
            elif path in {"/api/sources/search", "/api/sources/fetch"}:
                if not self.server.provider_lock.acquire(blocking=False):
                    self._send(429, {"error": "A data request is already running"})
                    return
                try:
                    value = (
                        search_sources(payload.get("query", ""), payload.get("catalog", "socrata"))
                        if path.endswith("search")
                        else fetch_source(payload.get("config", {}), payload.get("credential"))
                    )
                finally:
                    self.server.provider_lock.release()
            elif path == "/api/compute":
                from .compute import run_compute

                if not self.server.provider_lock.acquire(blocking=False):
                    self._send(429, {"error": "A user-service/data request is already running"})
                    return
                try:
                    value = run_compute(
                        payload.get("connection", {}),
                        payload.get("request", {}),
                        payload.get("credential"),
                    )
                finally:
                    self.server.provider_lock.release()
            elif path == "/api/connections/test":
                from .local_inference import call_llm

                response = call_llm(
                    payload.get("connection", {}),
                    'Return strict JSON only: {"probability":0.5}',
                    payload.get("credential"),
                )
                value = {
                    "status": "connected",
                    "reported_model": response["reported_model"],
                    "text": response["text"],
                    "completion_tokens": response["completion_tokens"],
                    "latency_seconds": response["latency_seconds"],
                }
            elif path == "/api/preset":
                value = preset(
                    payload.get("name", "sma_cross"),
                    fast=int(payload.get("fast", 20)),
                    slow=int(payload.get("slow", 50)),
                    amount=float(payload.get("amount", 100)),
                    threshold=float(payload.get("threshold", 5)),
                )
            elif path == "/api/settings/save":
                save_credential(payload.get("key", ""), payload.get("consent") is True)
                value = credential_status()
            elif path == "/api/settings/remove":
                remove_credential()
                value = credential_status()
            elif path in {"/api/feed", "/api/weather", "/api/settings/test"}:
                if not self.server.provider_lock.acquire(blocking=False):
                    self._send(429, {"error": "A provider request is already in progress"})
                    return
                try:
                    last = self.server.last_refresh.get(path)
                    now = time.monotonic()
                    if last is not None and now - last < 60:
                        raise ValueError(
                            "Wait at least 60 seconds between requests to this provider"
                        )
                    self.server.last_refresh[path] = now
                    if path == "/api/feed":
                        value = kraken_snapshot()
                    elif path == "/api/weather":
                        value = open_meteo(
                            float(payload["latitude"]),
                            float(payload["longitude"]),
                            payload["start"],
                            payload["end"],
                        )
                        value["csv"] = events_csv(value["events"])
                    else:
                        value = alpha_vantage_test(load_credential())
                finally:
                    self.server.provider_lock.release()
            elif path == "/api/shutdown":
                value = {"status": "stopping"}
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._send(404, {"error": "Not found"})
                return
            self._send(200, value)
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            self._send(400, {"error": str(error)[:500]})
        except Exception:
            self._send(
                500,
                {
                    "error": "Research operation failed; check the input and retry. No credentials are logged."
                },
            )


def make_server(port: int = 8765) -> LocalServer:
    return LocalServer(port)
