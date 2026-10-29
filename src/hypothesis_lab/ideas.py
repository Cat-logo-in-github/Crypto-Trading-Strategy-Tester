"""Translate research questions into inspectable data requirements, never invented data."""

from __future__ import annotations

import re


def plan_idea(query: str, fields: list[str] | None = None) -> dict:
    if not isinstance(query, str) or not 5 <= len(query.strip()) <= 2000:
        raise ValueError("Describe the question in 5..2,000 characters")
    text = query.strip()
    lower = text.casefold()
    stop = set(
        "a an the when whenever if then buy sell bitcoin btc stock stocks price market strategy trading trade invest test whether does how would work works worked want data dataset model probability prediction predict predictions forecast output above below greater less than increase increases increasing decrease decreases decreasing by of in is are and or to for from with on me my some any about tell find search use using returns return based track tracking correlate correlation long short hold go goes up down".split()
    )
    phrase = re.sub(r"[$€£]?\d+(?:\.\d+)?%?|[<>]=?|\b\d+[- ](?:day|bar|week)s?\b", " ", lower)
    words = [word for word in re.findall(r"[a-z][a-z0-9_'-]+", phrase) if word not in stop]
    terms = " ".join(dict.fromkeys(word.replace("_", " ") for word in words))[:180]
    if not terms:
        terms = text[:180]
    requested = []
    for field in fields or []:
        alias = re.sub(r"[^a-z0-9]", "", field.casefold())
        if alias and alias in re.sub(r"[^a-z0-9]", "", lower):
            requested.append(field)
    signal = (
        "threshold"
        if re.search(r"above|below|greater|less|[<>]", lower)
        else "change"
        if re.search(r"rising|falls|drops|increas|decreas|go up|goes up", lower)
        else "relationship"
    )
    inferred_model = bool(re.search(r"probability|predict|forecast|model|llm|tokens?", lower))
    window = re.search(r"(\d+)\s*[- ]?(bar|day|week|month)s?", lower)
    signals = [
        {
            "kind": "model_output" if inferred_model else signal,
            "candidate_fields": requested,
            "lookback": int(window[1]) if window else None,
            "lookback_unit": window[2] if window else None,
            "definition": "Map an explicit model output to a probability, numeric value, text match or reported token count, then apply the selected decision rule."
            if inferred_model
            else "Choose the exact measured column, transformation, threshold and trading action. The query alone does not establish a relationship.",
        }
    ]
    clarifications = []
    if not requested:
        clarifications.append(
            "Select the actual column that measures the idea after downloading/importing a candidate dataset."
        )
    if signal == "change" and not window:
        clarifications.append(
            "Choose how far back a rise/fall is measured; a change needs an explicit time window."
        )
    if not re.search(r"\$\d+|\b\d+\s*%\s*(?:of|portfolio|equity)", lower):
        clarifications.append("Choose cash budget or target portfolio weight.")
    return {
        "query": text,
        "search_terms": terms,
        "data_requirements": [
            {
                "concept": terms,
                "measurement": "Identify units and the measured quantity; verify it matches the requested concept.",
                "required_fields": [
                    "observation time",
                    "publication/availability time or an explicit assumption",
                    "numeric measurement or a defined text/categorical transformation",
                ],
                "geography": "User-selected; do not assume a location",
                "coverage": "Needs overlap with the chosen market and sufficient historical rows",
                "private_data": "Private store/merch sales require the owner's authorized export or API. Public vendor/permit data is a different proxy.",
            }
        ],
        "signals": signals,
        "clarifications": clarifications,
        "warnings": [
            "This is a proposed research definition. Review and map it before any backtest; no dataset or predictive relationship has been invented.",
            "Catalog matches can be proxies or unrelated assets. Read descriptions, units, publisher terms and temporal coverage before downloading.",
            "All built-in examples use labeled synthetic data until a user chooses a real source.",
        ],
    }
