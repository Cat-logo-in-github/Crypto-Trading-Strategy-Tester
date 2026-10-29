"""Editable dated cost scenarios; official commissions and assumptions stay distinct."""

from __future__ import annotations

VERIFIED_ON = "2026-10-29"
LATENCY_SOURCE = {
    "title": "CCXT Team, public order-book request timing by location (2026-07-16)",
    "url": "https://docs.ccxt.com/blog/how-far-is-your-exchange",
}


def execution_profiles() -> list[dict]:
    """Return fresh scenario descriptions; numeric user configuration is authoritative.

    These are snapshots, not account-specific fees or a historical fee database.
    No profile represents measured order-arrival, spread or fill slippage.
    """
    profiles: list[dict] = []
    official = [
        (
            "binance_regular_2026",
            "Binance regular spot — schedule snapshot",
            10,
            10,
            "Regular-user standard spot tier, without BNB discount, pair promotions or account-specific terms.",
            "Binance official Spot Trading Fee Rate",
            "https://www.binance.com/en/fee/trading",
        ),
        (
            "kraken_pro_tier1_2026",
            "Kraken Pro Tier 1 — schedule snapshot",
            40,
            80,
            "Rendered official Spot Crypto Tier 1 ($0+); geography/VPN, pair category and account tier can change applicability. This is not the older 25/40 bps schedule.",
            "Kraken official fee schedule, Spot Crypto",
            "https://www.kraken.com/features/fee-schedule",
        ),
        (
            "coinbase_advanced_us_entry_2026",
            "Coinbase Advanced US entry — schedule snapshot",
            50,
            90,
            "US spot entry tier announced 2026-09-16. EU/UK and other international entry rates differ; no account entitlement is inferred.",
            "Coinbase official Advanced fee update (2026-09-16)",
            "https://www.coinbase.com/blog/were-lowering-fees-for-many-active-traders-on-coinbase-advanced",
        ),
    ]
    profiles.append(
        {
            "id": "idealized_zero_cost",
            "name": "Idealized zero-cost boundary — software baseline",
            "execution": {
                "fee_bps": 0,
                "fixed_fee": 0,
                "spread_bps": 0,
                "slippage_bps": 0,
                "data_delay_ms": 0,
                "latency_ms": 0,
            },
            "as_of": VERIFIED_ON,
            "sources": [],
            "scope": "A deliberately idealized comparison for debugging. Not a real venue quote or realistic execution claim.",
            "fee_evidence": {"kind": "illustrative", "maker_bps": None, "taker_bps": None},
            "assumptions": [
                "All costs and delays are assumed zero. At an exact boundary this permits a next-open fill.",
                "No actual broker, account or market has been measured by this profile.",
            ],
        }
    )
    for identity, name, maker, taker, scope, title, url in official:
        profiles.append(
            {
                "id": identity,
                "name": name,
                "execution": {
                    "fee_bps": taker,
                    "fixed_fee": 0,
                    "spread_bps": 10,
                    "slippage_bps": 5,
                    "data_delay_ms": 100,
                    "latency_ms": 250,
                },
                "as_of": VERIFIED_ON,
                "sources": [{"title": title, "url": url}, dict(LATENCY_SOURCE)],
                "scope": scope,
                "fee_evidence": {
                    "kind": "official_schedule_snapshot",
                    "maker_bps": maker,
                    "taker_bps": taker,
                    "scope": scope,
                },
                "assumptions": [
                    "Only the commission rate is transcribed from the named official schedule; confirm your actual pair, jurisdiction and account rate.",
                    "The simulator uses market/taker-style fills. The maker rate is context, not a supported passive-order execution model.",
                    "Full spread 10 bps, additional adverse slippage 5 bps, fixed fee 0 quote units, data delay 100 ms and submit latency 250 ms are illustrative editable assumptions, not measured venue values.",
                    "CCXT's public-data time-to-first-byte measurements demonstrate geographic variation; they do not measure your order arrival, inference runtime or fills.",
                    "A positive delay just after a bar boundary may defer a full bar. Use finer data when that quantization is material.",
                    "Current fee snapshots are not historically point-in-time fee schedules and do not automatically change with simulated volume tiers.",
                ],
            }
        )
    profiles.append(
        {
            "id": "illustrative_cost_stress",
            "name": "Illustrative slow/wide cost stress",
            "execution": {
                "fee_bps": 100,
                "fixed_fee": 1,
                "spread_bps": 100,
                "slippage_bps": 50,
                "data_delay_ms": 1000,
                "latency_ms": 2000,
            },
            "as_of": VERIFIED_ON,
            "sources": [dict(LATENCY_SOURCE)],
            "scope": "A user-editable stress scenario in quote currency; no venue, country or instrument is represented.",
            "fee_evidence": {"kind": "illustrative", "maker_bps": None, "taker_bps": None},
            "assumptions": [
                "Every value is illustrative, including the 1 quote-unit per-fill charge.",
                "This sensitivity case is neither a measured worst case nor a guarantee of conservative execution.",
            ],
        }
    )
    return profiles
