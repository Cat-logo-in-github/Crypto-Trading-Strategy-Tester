"""Reproduce five exploratory public-data trials; never a point-in-time edge claim.

Install the source edition, then run:
python examples/public_data_research.py --directory my-public-research --fetch
This fetches public observations/prices from the user's network and writes only
inside the chosen directory. Without --fetch it requires that cached raw data.
The dates/definitions/costs are fixed; no threshold is selected by test returns.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import csv
import hashlib
import io
import json
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hypothesis_lab.algorithms import plan_algorithm
from hypothesis_lab.research import run_experiment

urls = {
    "market": "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400&start=2025-01-01T00:00:00Z&end=2025-10-01T00:00:00Z",
    "duck": "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Rubber_duck_debugging/daily/2025010100/2025100100",
    "paper": "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Toilet_paper/daily/2025010100/2025100100",
    "sourdough": "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Sourdough/daily/2025010100/2025100100",
    "weather": "https://archive-api.open-meteo.com/v1/archive?latitude=36.17&longitude=-115.14&start_date=2025-01-01&end_date=2025-10-01&daily=precipitation_sum,sunshine_duration&timezone=UTC",
    "quakes": "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=2025-01-01&endtime=2025-10-01&minmagnitude=4.5&orderby=time-asc&limit=20000",
}


def download(root):
    def fetch(item):
        name, url = item
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "HypothesisLabResearch/0.4 (student paper research; https://github.com/Cat-logo-in-github/Crypto-Trading-Strategy-Tester)"
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(8_000_001)
        if len(raw) > 8_000_000:
            raise ValueError("Public sample exceeded the 8MB verification bound")
        value = json.loads(raw)
        (root / (name + ".json")).write_bytes(raw)
        return name, {
            "status": "fetched",
            "bytes": len(raw),
            "url": url,
            "count": len(value.get("items", value.get("features", [])))
            if isinstance(value, dict)
            else len(value),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        report = dict(pool.map(fetch, urls.items()))
    url = "https://earthquake.usgs.gov/fdsnws/event/1/count?starttime=2025-01-01&endtime=2025-10-01&minmagnitude=4.5"
    with urllib.request.urlopen(url, timeout=30) as response:
        count = int(response.read(100))
    report["quake_count"] = {
        "url": url,
        "count": count,
        "bytes": len(str(count)),
        "status": "fetched",
    }
    (root / "fetch-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument(
        "--fetch", action="store_true", help="Explicitly download the bounded public histories"
    )
    args = parser.parse_args()
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    root = directory / "raw"
    root.mkdir(exist_ok=True)
    if args.fetch:
        download(root)
    fetch = json.loads((root / "fetch-report.json").read_text(encoding="utf-8"))
    out = directory
    start = datetime(2025, 1, 1, tzinfo=UTC)
    stop = datetime(2025, 10, 2, tzinfo=UTC)
    market = json.loads((root / "market.json").read_text(encoding="utf-8"))
    rows = sorted(
        {r[0]: r for r in market if start.timestamp() <= r[0] < stop.timestamp()}.values()
    )
    stream = io.StringIO()
    w = csv.writer(stream)
    w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
    for r in rows:
        w.writerow([datetime.fromtimestamp(r[0], UTC).isoformat(), r[3], r[2], r[1], r[4], r[5]])
    market_csv = stream.getvalue()
    (root / "market.csv").write_text(market_csv, encoding="utf-8")
    views = {
        key: {
            item["timestamp"][:8]: item["views"]
            for item in json.loads((root / (key + ".json")).read_text(encoding="utf-8"))["items"]
        }
        for key in ["duck", "paper", "sourdough"]
    }
    interest = [
        {
            "observed_at": (
                datetime.strptime(day, "%Y%m%d").replace(tzinfo=UTC) + timedelta(days=1)
            ).isoformat(),
            "duck_views": views["duck"][day],
            "paper_views": views["paper"][day],
            "sourdough_views": views["sourdough"][day],
        }
        for day in sorted(set.intersection(*(set(value) for value in views.values())))
    ]
    weather = json.loads((root / "weather.json").read_text(encoding="utf-8"))["daily"]
    rain = [
        {
            "observed_at": (
                datetime.fromisoformat(day).replace(tzinfo=UTC) + timedelta(days=1)
            ).isoformat(),
            "rain_mm": weather["precipitation_sum"][i],
            "sunshine_seconds": weather["sunshine_duration"][i],
        }
        for i, day in enumerate(weather["time"])
    ]
    quakes = json.loads((root / "quakes.json").read_text(encoding="utf-8"))
    assert fetch["quake_count"]["count"] == len(quakes["features"]) < 20000
    quake_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "observed_at": datetime.fromtimestamp(
                        f["properties"]["time"] / 1000, UTC
                    ).isoformat(),
                    "available_at": datetime.fromtimestamp(
                        f["properties"]["updated"] / 1000, UTC
                    ).isoformat(),
                    "magnitude": f["properties"]["mag"],
                },
                "geometry": f["geometry"],
            }
            for f in quakes["features"]
        ],
    }
    execution = {
        "initial_cash": 10000,
        "fee_bps": 90,
        "spread_bps": 10,
        "slippage_bps": 5,
        "data_delay_ms": 100,
        "latency_ms": 250,
    }
    base = {
        "market_csv": market_csv,
        "execution": execution,
        "provenance_note": "Actual Coinbase Exchange daily BTC-USD and public observations retrieved 2026-10-30. Daily bar simulation; no quote/liquidity archive. Fees are an explicit 90bps scenario, not verified 2025 fees.",
    }
    mapping = {
        "observed_at_column": "observed_at",
        "availability_mode": "lag",
        "availability_lag_hours": 48,
        "max_age_hours": 96,
        "timezone": "UTC",
        "field_columns": ["duck_views", "paper_views", "sourdough_views"],
    }

    def rule(name, words, fields, data=interest, config=mapping, format="json"):
        plan = plan_algorithm(words, fields)
        assert plan["executable"], plan
        return {
            **base,
            "name": name,
            "mode": "algorithm",
            "feature_data": json.dumps(data),
            "feature_format": format,
            "feature_mapping": config,
            "algorithm": plan["draft"],
        }, plan

    trials = []
    trials.append(
        rule(
            "Rubber-duck debugging rally",
            "Buy $100 when duck views is above its seven-bar average; sell when duck views is below its seven-bar average.",
            ["duck_views"],
        )
    )
    trials.append(
        rule(
            "Toilet-paper panic scroll",
            "Buy $100 when paper views rises by more than 10% over seven bars; sell when paper views falls by more than 5% over seven bars.",
            ["paper_views"],
        )
    )
    trials.append(
        (
            {
                **base,
                "name": "Sourdough predicts panic browsing",
                "mode": "model",
                "feature_data": json.dumps(interest),
                "feature_format": "json",
                "feature_mapping": mapping,
                "model_config": {
                    "feature_names": ["sourdough_views", "duck_views"],
                    "target_type": "condition",
                    "target_condition": "paper_views > mean(paper_views,7)",
                    "horizon": 3,
                    "epochs": 150,
                    "l2_candidates": [0.01, 0.1, 1],
                    "decision": {
                        "comparison": ">",
                        "threshold": 0.55,
                        "when_true": {"target_weight": 0.5},
                        "when_false": "exit",
                    },
                },
            },
            {
                "executable": True,
                "note": "Explicit reviewed natural-language target: predict whether the available toilet-paper pageviews will exceed their trailing seven-bar average three bars ahead, using sourdough and rubber-duck interest; target 50% BTC when probability exceeds .55.",
            },
        )
    )
    trials.append(
        rule(
            "Rain in the desert",
            "Buy $100 when rain mm is above 0.1; sell when rain mm is below 0.1.",
            ["rain_mm"],
            rain,
            {
                "observed_at_column": "observed_at",
                "availability_mode": "lag",
                "availability_lag_hours": 168,
                "max_age_hours": 192,
                "timezone": "UTC",
                "field_columns": ["rain_mm", "sunshine_seconds"],
            },
        )
    )
    trials.append(
        rule(
            "A shaky planet and digital gold",
            "Buy $100 when event count is above its seven-bar average; sell when event count is below its seven-bar average.",
            ["event_count"],
            quake_data,
            {
                "observed_at_column": "observed_at",
                "available_at_column": "available_at",
                "availability_mode": "column",
                "max_age_hours": 96,
                "field_columns": [],
                "aggregation": {"frequency": "day", "operation": "count", "fields": []},
            },
            "geojson",
        )
    )
    results = []
    for body, plan in trials:
        result = run_experiment(body, persist=False)
        stress = copy.deepcopy(body)
        stress["execution"]["fee_bps"] = 180
        expensive = run_experiment(stress, persist=False)
        # Freeze row order, move all observation availability beyond the evaluation.
        blocked = copy.deepcopy(body)
        blocked["feature_mapping"].update(availability_mode="lag", availability_lag_hours=24 * 2000)
        try:
            negative = run_experiment(blocked, persist=False)
            negative_control = {
                "fills": len(negative["strategy"]["fills"]),
                "blocked_future_data": not negative["strategy"]["fills"],
            }
        except ValueError as e:
            negative_control = {"blocked_future_data": True, "error": str(e)}
        identity = body["name"].lower().replace(" ", "-")
        (root / (identity + "-payload.json")).write_text(json.dumps(body), encoding="utf-8")
        (root / (identity + "-result.json")).write_text(json.dumps(result), encoding="utf-8")
        entry = {
            "name": body["name"],
            "plain_language": plan.get("note") or plan["draft"],
            "mode": body["mode"],
            "compiled_automatically": bool("draft" in plan),
            "evaluation": result["evaluation"],
            "return": result["summary"]["total_return"],
            "benchmark_return": result["benchmark"]["metrics"]["total_return"],
            "excess_return": result["summary"]["excess_return"],
            "fills": len(result["strategy"]["fills"]),
            "fees": result["summary"]["fees_paid"],
            "drawdown": result["summary"]["max_drawdown"],
            "cost_stress_return": expensive["summary"]["total_return"],
            "evidence": result["evidence"],
            "model_test": result["model"]["test"] if result.get("model") else None,
            "negative_control": negative_control,
            "dataset_identity": result["dataset"]["identity"],
        }
        results.append(entry)
        print(body["name"], entry["return"], entry["benchmark_return"], entry["fills"], flush=True)
    report = {
        "date": "2026-10-30",
        "status": "Actual public data, exploratory retrospective tests; not verified point-in-time edge evidence",
        "market": "Coinbase Exchange BTC-USD daily candles",
        "market_bars": len(rows),
        "sources": fetch,
        "raw_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.glob("*.json")
            if p.name
            in [
                "market.json",
                "duck.json",
                "paper.json",
                "sourdough.json",
                "weather.json",
                "quakes.json",
            ]
        },
        "execution": execution,
        "publication_assumptions": [
            "Wikimedia days are measured at UTC day completion; an explicit additional 48-hour historical lag is assumed, not verified release vintages. Counts reflect the retrieved archive and may be revised.",
            "Open-Meteo reanalysis days complete at UTC day end; a seven-day lag is only an exploratory scenario, not a reconstruction of forecast/reanalysis vintages. This trial trades reported rainfall, not forecast skill.",
            "USGS uses supplied actual last-update timestamps; daily event counts become eligible only after the completed bucket and every included update. Historical revisions published after the test period are excluded. Count reflects the complete returned query, not a live original-release archive.",
            "All five thresholds and model settings were fixed before these fetched returns were inspected. Five related hypotheses and a single selected period remain multiple exploratory tests.",
        ],
        "trials": results,
        "limits": [
            "No actual private sales, borrowing data, options chains, funding tape or professional broker entitlement was supplied.",
            "These actual-data tests use the declared coarse bar backend; fine-event and multi-contract paths are independently tested with controlled quote/cash-flow fixtures.",
            "No threshold was tuned to improve the reported test returns. Three predeclared model penalties use validation only; final model return is held-out. Positive historical return is not evidence of repeatable future profitability.",
        ],
    }
    (out / "public-strategy-results.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    lines = [
        "# Five real public-data exploratory trials — 2026-10-30",
        "",
        report["status"] + ".",
        "",
        f"Market: {len(rows)} actual Coinbase Exchange BTC-USD daily bars. Rules use the available sample; the trained model trades only its final held-out portion. The benchmark always uses the same actual evaluation window and costs.",
        "",
        "| Question | Strategy | Matched buy/hold | Fills | Fee stress return |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for r in results:
        lines.append(
            f"| {r['name']} | {r['return']:.2%} | {r['benchmark_return']:.2%} | {r['fills']} | {r['cost_stress_return']:.2%} |"
        )
    lines += [
        "",
        "Trading fee scenario is 90 bps per fill, full spread 10 bps, extra slippage 5 bps; 100 ms data and 250 ms order delay. Daily-bar quantization applies. Stress doubles the fee to 180 bps; other settings stay fixed. These are assumptions, not a verified 2025 venue-fee archive.",
        "",
        "## Definitions and evaluation windows",
        "",
    ]
    for r in results:
        lines += [
            f"### {r['name']}",
            "",
            json.dumps(r["plain_language"], ensure_ascii=False),
            f"Evaluation: {r['evaluation']['start']} to {r['evaluation']['end']}; {r['evaluation']['bars']} valued bars. Fees: {r['fees']:.2f} USD; maximum drawdown {r['drawdown']:.2%}. Future-publication negative control: {r['negative_control']}.",
            "",
        ]
    lines += (
        ["## Publication assumptions", ""]
        + ["- " + s for s in report["publication_assumptions"]]
        + ["", "## Sources", ""]
    )
    for key, item in fetch.items():
        lines.append(f"- [{key}: fetched {item.get('bytes', 0):,} bytes]({item['url']})")
    lines += (
        ["", "## Limits", ""]
        + ["- " + s for s in report["limits"]]
        + [
            "",
            "Full metrics, paired block-bootstrap uncertainty, model diagnostics, query URLs and raw-data hashes are in public-strategy-results.json. Raw downloaded datasets and full intermediate payloads stay in the chosen raw/output directory, outside the release ZIP.",
        ]
    )
    (out / "public-strategy-results.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
