"""AI plan writer: Strands Agents on Amazon Bedrock.

The agent gets two tools bound to ONE ponds.json snapshot (the one the user asked for), so it
cannot read other dates. Its draft must pass the number guard; on failure it gets one retry
with the offending numbers listed, then we give up and the template plan stays.
"""
from __future__ import annotations

import os
import re
from typing import Callable

from logic.guard import invented_numbers

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-5-5")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
MAX_TOKENS = 8000
LANG_NAME = {"en": "English", "mr": "Marathi"}

SYSTEM_PROMPT = """You draft water-scarcity action plans for district officials in Maharashtra, India, using satellite measurements from Talaab. The officials will act on your plan (send tankers, restrict use, inspect ponds for illegal pumping), so it must be accurate and easy to scan.

Facts come only from your tools. Call get_ponds first; call get_pond for detail on a pond if you need it.

Write Markdown in the requested language:
- A title naming the region and the as-of date, then two or three sentences on the overall situation, including the sun's share (sunShareMm: evaporation over the last 45 days).
- "Already dry" ponds first: these need alternative supply now.
- Then one section per scarcity period in which ponds are likely to dry up, using the government's periods Oct–Dec, Jan–Mar and Apr–Jun. A pond likely to last past June lasts until the monsoon. Most urgent first.
- For each pond: its id in bold, its place, water area now and max (ha), the dry-by range (earliest to latest, with the likely date) and one concrete action.
- A section listing ponds flagged "faster-than-sun" for inspection, with how many times faster than neighbours they shrink. Say plainly this suggests possible unauthorised extraction, not proof.
- Ponds with status "unknown" (hidden by cloud) need a ground check.

Rules:
- Copy every number exactly as the tools return it. Do not compute new numbers (no percentages, totals or rounding); counting ponds is fine. Write dates as day month year.
- Always present dry-by as a range, never as a single certain date.
- Never invent ponds, villages, populations, tanker counts, costs or budgets.
- If the region name says it is a replay, say the plan is a replay of past data.
- In Marathi, write natural Marathi for officials and keep pond ids and numbers in ASCII digits.
- Output only the plan."""


def compact_doc(doc: dict) -> dict:
    """What get_ponds returns: everything except per-pass histories (kept for get_pond)."""
    return {
        "region": doc["region"],
        "asOf": doc["asOf"],
        "sunShareMm": doc.get("sunShareMm"),
        "scenesClear": sum(s.get("status") == "ok" for s in doc.get("scenes", [])),
        "scenesSuspect": sum(s.get("status") == "suspect" for s in doc.get("scenes", [])),
        "ponds": [{k: v for k, v in p.items() if k != "history"} for p in doc["ponds"]],
    }


def make_tools(doc: dict) -> list:
    from strands import tool

    @tool
    def get_ponds(region: str, as_of: str) -> dict:
        """Get every pond in the region with its status, areas, dry-by range and flags.

        Args:
            region: region id, e.g. latur-2024
            as_of: snapshot date YYYY-MM-DD
        """
        if region != doc["region"]["id"] or as_of != doc["asOf"]:
            return {"error": f"only region {doc['region']['id']} as of {doc['asOf']} is available"}
        return compact_doc(doc)

    @tool
    def get_pond(pond_id: str) -> dict:
        """Get one pond including its full history of measured water area per satellite pass.

        Args:
            pond_id: pond id, e.g. P003
        """
        for p in doc["ponds"]:
            if p["id"] == pond_id:
                return p
        return {"error": f"no pond {pond_id}"}

    return [get_ponds, get_pond]


def strands_runner(doc: dict) -> Callable[[str], str]:
    """Return a function prompt -> text backed by one Strands agent (keeps conversation for retry)."""
    from strands import Agent
    from strands.models import BedrockModel

    model = BedrockModel(model_id=MODEL_ID, region_name=AWS_REGION, max_tokens=MAX_TOKENS)
    agent = Agent(model=model, tools=make_tools(doc), system_prompt=SYSTEM_PROMPT, callback_handler=None)
    return lambda prompt: str(agent(prompt))


def write_plan(doc: dict, language: str, runner: Callable[[str], str] | None = None) -> dict:
    """Generate and validate an AI plan. Raises ValueError if the guard rejects it twice."""
    run = runner or strands_runner(doc)
    prompt = (
        f"Write the {LANG_NAME[language]} water-scarcity action plan for region "
        f"{doc['region']['id']} as of {doc['asOf']}."
    )
    markdown = run(prompt).strip()
    bad = invented_numbers(markdown, doc)
    if bad:
        markdown = run(
            "These numbers in your plan are not in the data: "
            + ", ".join(sorted(bad))
            + ". Rewrite the full plan using only numbers exactly as the tools return them."
        ).strip()
        bad = invented_numbers(markdown, doc)
        if bad:
            raise ValueError(f"plan rejected by number guard: {sorted(bad)}")

    known = {p["id"] for p in doc["ponds"]}
    cited = list(dict.fromkeys(i for i in re.findall(r"P\d{3,4}", markdown) if i in known))
    return {"markdown": markdown, "pondIds": cited, "source": "bedrock", "model": MODEL_ID}
