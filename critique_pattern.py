"""Critique-pattern orchestration for Coolblue 'green zone' upsell copy.

A prompt-owner agent iterates a Dutch system prompt and small-model settings
until a critic agent approves a BATCH of generated upsell lines — one per
row in new_objective.md/data.json.

Hard constraint per line: max 100 chars, Dutch B1, 'je krijgt' style, no
reference to the previous (from_value) option.

Run: python critique_pattern.py
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agent import Agent, run_full_turn

load_dotenv()


# ---------------------------------------------------------------------------
# Task configuration
# ---------------------------------------------------------------------------

DATA_PATH = Path(__file__).parent / "new_objective.md" / "data.json"
DATA: List[dict] = json.loads(DATA_PATH.read_text(encoding="utf-8"))

MAX_CHARS = 100

OBJECTIVE = (
    "Genereer per rij één korte, klantgerichte Nederlandse upsell-zin. "
    "Maximaal 100 tekens (incl. spaties), B1-niveau, actief, in 'je krijgt'-"
    "stijl. Beschrijf alleen het voordeel van de aangeboden waarde — noem "
    "of vergelijk de vorige waarde NIET."
)

# Fields surfaced to the GENERATOR. from_* is deliberately withheld so the
# model cannot leak or compare to the previous option.
GENERATOR_INPUT_FIELDS = (
    "consideration_name",
    "to_value",
    "to_description",
    "to_pro",
    "to_con",
)

# Style benchmarks from objective.md. Only the CRITIC sees these — the
# generator must learn the voice from the prompt instructions, not by
# parroting examples.
STYLE_EXAMPLES = [
    {
        "consideration": "Vulgewicht",
        "from": "8kg",
        "to": "9kg",
        "good": "Je krijgt extra ruimte voor handdoeken en beddengoed, dus je wast meer in één keer.",
    },
    {
        "consideration": "Vulgewicht",
        "from": "9kg",
        "to": "10kg",
        "good": "Je krijgt genoeg ruimte voor grote was zoals dekbedden en dekens in één keer.",
    },
    {
        "consideration": "Processor",
        "from": "Intel Core i3",
        "to": "Intel Core i5",
        "good": "Je krijgt genoeg vermogen om vlot te browsen, in Office te werken en meerdere tabs te openen.",
    },
    {
        "consideration": "Processor",
        "from": "Intel Core i5",
        "to": "Intel Core i7",
        "good": "Je krijgt meer rekenkracht voor zwaar multitasken, zoals veel apps en tabs tegelijk.",
    },
]

ALLOWED_GENERATION_MODELS = {
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
}

REASONING_MODEL = "gpt-5.4"
MAX_ITERATIONS = 4


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

WIDTH = 80


def _banner(title: str, char: str = "=") -> None:
    print()
    print(char * WIDTH)
    print(f"  {title}")
    print(char * WIDTH)


def _section(title: str) -> None:
    print()
    print(f"--- {title} ".ljust(WIDTH, "-"))


def _kv(label: str, value: object, width: int = 20) -> None:
    print(f"  {label.ljust(width)} {value}")


def _block(text: str) -> None:
    print()
    for line in str(text).splitlines() or [""]:
        print(f"  {line}")
    print()


# ---------------------------------------------------------------------------
# Versioning + persistence
# ---------------------------------------------------------------------------

@dataclass
class PromptVersion:
    version: int
    parent_version: Optional[int]
    note: str
    prompt: str
    created_at: str  # ISO-8601


@dataclass
class GenerationConfig:
    model: str = "gpt-5.4-mini"
    temperature: float = 0.4
    max_output_tokens: int = 120
    last_outputs: List[dict] = field(default_factory=list)
    iteration: int = 0
    current_version: int = 0
    prompt_versions: List[PromptVersion] = field(default_factory=list)
    history: List[dict] = field(default_factory=list)
    run_dir: Optional[Path] = None

    @property
    def prompt(self) -> str:
        return self.prompt_versions[self.current_version - 1].prompt


config = GenerationConfig()


RUNS_ROOT = Path(__file__).parent / "runs"


def _init_run_dir() -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    run_dir = RUNS_ROOT / timestamp
    (run_dir / "prompts").mkdir(parents=True, exist_ok=True)
    (run_dir / "iterations").mkdir(parents=True, exist_ok=True)
    return run_dir


def _persist_prompt_version(pv: PromptVersion) -> Path:
    path = config.run_dir / "prompts" / f"v{pv.version:03d}.md"
    parent = "—" if pv.parent_version is None else f"v{pv.parent_version:03d}"
    body = (
        f"---\n"
        f"version: {pv.version}\n"
        f"parent_version: {parent}\n"
        f"created_at: {pv.created_at}\n"
        f"note: {json.dumps(pv.note)}\n"
        f"---\n\n"
        f"{pv.prompt}\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def _persist_iteration(record: dict) -> Path:
    path = config.run_dir / "iterations" / f"iter-{record['iteration']:03d}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _persist_manifest() -> None:
    manifest = {
        "objective": OBJECTIVE,
        "max_chars": MAX_CHARS,
        "reasoning_model": REASONING_MODEL,
        "allowed_generation_models": sorted(ALLOWED_GENERATION_MODELS),
        "current_version": config.current_version,
        "iterations_run": config.iteration,
        "current_settings": {
            "model": config.model,
            "temperature": config.temperature,
            "max_output_tokens": config.max_output_tokens,
        },
        "prompt_versions": [
            {
                "version": pv.version,
                "parent_version": pv.parent_version,
                "note": pv.note,
                "created_at": pv.created_at,
                "file": f"prompts/v{pv.version:03d}.md",
            }
            for pv in config.prompt_versions
        ],
        "iterations": [
            {
                "iteration": h["iteration"],
                "prompt_version": h["prompt_version"],
                "model": h["model"],
                "temperature": h["temperature"],
                "approved": h["verdict"]["approved"],
                "n_over_max_chars": h["stats"]["n_over_max_chars"],
                "file": f"iterations/iter-{h['iteration']:03d}.json",
            }
            for h in config.history
        ],
    }
    (config.run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _create_prompt_version(prompt: str, note: str) -> PromptVersion:
    next_version = len(config.prompt_versions) + 1
    parent = config.current_version or None
    pv = PromptVersion(
        version=next_version,
        parent_version=parent,
        note=note,
        prompt=prompt,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    config.prompt_versions.append(pv)
    config.current_version = next_version
    _persist_prompt_version(pv)
    _persist_manifest()
    return pv


# ---------------------------------------------------------------------------
# Generator-input filtering
# ---------------------------------------------------------------------------

def _top_rank_per_consideration() -> dict:
    by_cons: dict = {}
    for row in DATA:
        c = row["consideration_name"]
        by_cons[c] = min(by_cons.get(c, row["to_rank"]), row["to_rank"])
    return by_cons


_TOP_RANK = _top_rank_per_consideration()


def _generator_input(row: dict) -> dict:
    payload = {k: row[k] for k in GENERATOR_INPUT_FIELDS}
    payload["is_top_tier"] = row["to_rank"] == _TOP_RANK[row["consideration_name"]]
    return payload


# ---------------------------------------------------------------------------
# Prompt-owner tools
# ---------------------------------------------------------------------------

def update_prompt(new_prompt: str, note: str) -> str:
    """Create a new versioned system prompt for the generator.

    The new prompt fully replaces the previous one — include everything that
    should remain. Provide a short `note` (1–2 sentences) describing what
    you changed and why; this is recorded with the version.
    """
    pv = _create_prompt_version(new_prompt, note)
    parent = "—" if pv.parent_version is None else f"v{pv.parent_version:03d}"
    _section(f"tool: update_prompt (v{pv.version:03d}, parent {parent})")
    _kv("note:", note)
    _block(new_prompt)
    return (
        f"Prompt v{pv.version:03d} created from {parent} "
        f"({len(new_prompt)} chars). Saved to prompts/v{pv.version:03d}.md."
    )


def update_model_settings(
    model: str, temperature: float, max_output_tokens: int
) -> str:
    """Pick the generation model and tune its sampling parameters.

    Allowed models (cheap mini/nano variants only):
      gpt-5.4-mini, gpt-5.4-nano, gpt-4.1-mini, gpt-4.1-nano
    temperature: 0.0–2.0. max_output_tokens: 50–4000. Keep tokens low
    (~80–150) — each output is one short sentence.
    """
    if model not in ALLOWED_GENERATION_MODELS:
        return (
            f"Error: '{model}' not allowed. Choose from "
            f"{sorted(ALLOWED_GENERATION_MODELS)}."
        )
    if not 0.0 <= temperature <= 2.0:
        return "Error: temperature must be in [0.0, 2.0]."
    if not 50 <= max_output_tokens <= 4000:
        return "Error: max_output_tokens must be in [50, 4000]."
    config.model = model
    config.temperature = temperature
    config.max_output_tokens = max_output_tokens
    _section("tool: update_model_settings")
    _kv("model:", model)
    _kv("temperature:", temperature)
    _kv("max_output_tokens:", max_output_tokens)
    print()
    return (
        f"Settings: model={model}, temperature={temperature}, "
        f"max_output_tokens={max_output_tokens}"
    )


def run_generation_pipeline() -> dict:
    """Run one batch generate+critique cycle with the current prompt.

    Generates one upsell line for every row in the dataset using the current
    system prompt. Each row's user message is a JSON object with only the
    fields the generator is allowed to see (no from_*). The full batch is
    then evaluated by the Critic as a whole.

    Returns approval, critique, char-length stats, and a sample of outputs.
    """
    config.iteration += 1
    prompt_version = config.current_version
    _banner(
        f"ITERATION {config.iteration}  "
        f"(prompt v{prompt_version:03d}, model {config.model})"
    )

    _section("settings")
    _kv("model:", config.model)
    _kv("temperature:", config.temperature)
    _kv("max_output_tokens:", config.max_output_tokens)
    _kv("prompt_version:", f"v{prompt_version:03d}")

    _section(f"prompt v{prompt_version:03d}")
    _block(config.prompt)

    gen_llm = ChatOpenAI(
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_output_tokens,
    )

    _section(f"generating {len(DATA)} upsell lines")
    outputs: List[dict] = []
    for i, row in enumerate(DATA):
        gen_input = _generator_input(row)
        gen_response = gen_llm.invoke([
            SystemMessage(content=config.prompt),
            HumanMessage(content=json.dumps(gen_input, ensure_ascii=False, indent=2)),
        ])
        line = gen_response.content.strip().strip('"').strip()
        outputs.append({
            "row_index": i,
            "row": row,
            "generator_input": gen_input,
            "output": line,
            "char_count": len(line),
        })
        flag = "  ⚠" if len(line) > MAX_CHARS else "   "
        head = (
            f"{row['consideration_name'][:18]:<18} "
            f"{row['from_value']:>6} → {row['to_value']:<6}"
        )
        print(f"  [{i + 1:02d}/{len(DATA)}] [{len(line):3d}c{flag}] {head}: {line}")

    config.last_outputs = outputs

    n_over = sum(1 for o in outputs if o["char_count"] > MAX_CHARS)
    char_lengths = [o["char_count"] for o in outputs]
    stats = {
        "n_rows": len(outputs),
        "n_over_max_chars": n_over,
        "max_chars_seen": max(char_lengths),
        "avg_chars": round(sum(char_lengths) / len(char_lengths), 1),
    }

    verdict = _run_critique(outputs)

    _section(f"verdict (iteration {config.iteration})")
    _kv("approved:", verdict["approved"])
    _kv("reason:", verdict["reason"])
    _kv("over-limit lines:", f"{n_over}/{len(outputs)}")
    _kv("char range:", f"{min(char_lengths)}–{max(char_lengths)} (avg {stats['avg_chars']})")
    print()
    print("  critique:")
    _block(verdict["critique"])

    record = {
        "iteration": config.iteration,
        "prompt_version": prompt_version,
        "model": config.model,
        "temperature": config.temperature,
        "max_output_tokens": config.max_output_tokens,
        "prompt": config.prompt,
        "outputs": outputs,
        "stats": stats,
        "verdict": verdict,
    }
    config.history.append(record)
    iter_path = _persist_iteration(record)
    _persist_manifest()
    _kv("saved:", iter_path.relative_to(config.run_dir.parent))

    return {
        "iteration": config.iteration,
        "prompt_version": prompt_version,
        "approved": verdict["approved"],
        "critique": verdict["critique"],
        "judge_reason": verdict["reason"],
        "stats": stats,
        "sample_outputs": [
            {
                "consideration": o["row"]["consideration_name"],
                "from": o["row"]["from_value"],
                "to": o["row"]["to_value"],
                "chars": o["char_count"],
                "line": o["output"],
            }
            for o in outputs[:5]
        ],
    }


# ---------------------------------------------------------------------------
# Critic tools
# ---------------------------------------------------------------------------

_pending_verdict: dict = {"critique": None, "approved": None, "reason": None}


def write_critique(critique: str) -> str:
    """Record specific, actionable feedback on the prompt template.

    Point at concrete defects across rows ("rows 3,7 leak '8 GB'", "row 11 is
    113 chars", "tone too generic on storage rows", "missing je-krijgt
    opening on 5/13") and what to change in the system prompt.
    """
    _pending_verdict["critique"] = critique
    _section("tool: write_critique")
    _block(critique)
    return "Critique recorded."


def judge(approved: bool, reason: str) -> str:
    """Final verdict on the full batch. Calling this ends the critique pass.

    Approve ONLY when ALL hard constraints pass on ALL rows AND the copy
    quality is genuinely good across the batch.
    """
    _pending_verdict["approved"] = approved
    _pending_verdict["reason"] = reason
    _section("tool: judge")
    _kv("approved:", approved)
    _kv("reason:", reason)
    print()
    return f"Verdict recorded: approved={approved}."


def run_eval(python_code: str) -> str:
    """Run a Python snippet against the current batch.

    Pre-bound (do NOT redefine):
      - rows: list of dicts, each {row_index, row, generator_input, output,
              char_count}. row contains the FULL data row including from_*.
      - outputs: list of strings (just the generated lines).
      - MAX_CHARS: the hard char limit (100).
      - re, json: imported modules.

    Assign your answer to a variable named `result`. Comprehensions and
    generator expressions work normally — names defined at the top of the
    snippet are visible inside them.

    Examples:
        result = [(r["row_index"], r["char_count"]) for r in rows
                  if r["char_count"] > MAX_CHARS]
        result = [r["row_index"] for r in rows
                  if r["row"]["from_value"].lower() in r["output"].lower()]
    """
    _section("tool: run_eval")
    _block(python_code)
    if not config.last_outputs:
        result_str = "Error: no outputs to evaluate yet."
    else:
        import re as _re
        ns = {
            "rows": config.last_outputs,
            "outputs": [o["output"] for o in config.last_outputs],
            "MAX_CHARS": MAX_CHARS,
            "re": _re,
            "json": json,
        }
        try:
            # Single namespace: comprehensions/genexps see top-level names.
            exec(python_code, ns)
            if "result" not in ns:
                result_str = "Error: snippet did not assign a `result` variable."
            else:
                result_str = f"result = {ns['result']!r}"
        except Exception as e:
            result_str = f"Error: {type(e).__name__}: {e}"
    _kv("=>", result_str[:500] + ("…" if len(result_str) > 500 else ""))
    print()
    return result_str


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

critique_agent = Agent(
    name="Critic",
    instructions=(
        "You review a BATCH of Dutch upsell lines for the Coolblue 'green "
        "zone'. Each line corresponds to one row in the dataset and was "
        "produced by the same system prompt (the artifact under iteration).\n\n"
        f"HARD CONSTRAINTS per line (all must hold for every row):\n"
        f"- Length ≤ {MAX_CHARS} characters incl. spaces.\n"
        "- Dutch, B1-level, single short active sentence.\n"
        "- 'Je krijgt …' or equivalent direct customer-centric phrasing.\n"
        "- NEVER mentions or implies the previous (from_value) option. Watch "
        "for substring leaks of from_value (e.g. '8 GB', 'i5'), comparative "
        "phrasing ('meer dan', 'beter dan vorig', 'in plaats van'), and "
        "negation referring to the prior tier.\n"
        "- Describes the BENEFIT of to_value in plain customer terms; no "
        "raw spec parroting; no jargon.\n\n"
        "QUALITY BAR:\n"
        "- Recognisable real-life situation; persuasive in one breath.\n"
        "- For top-tier offers (`is_top_tier == True`), use 'beste van het "
        "beste' / 'nooit meer ergens over inzitten'-tonality where it fits "
        "naturally.\n\n"
        "STYLE BENCHMARK (voice — do not template, do not show to generator):\n"
        + json.dumps(STYLE_EXAMPLES, ensure_ascii=False, indent=2)
        + "\n\nPROCESS:\n"
        "1. run_eval has these pre-bound: `rows` (list of {row_index, row, "
        "generator_input, output, char_count}), `outputs` (list[str]), "
        "`MAX_CHARS`, `re`, `json`. Do NOT redefine them.\n"
        "2. Run cheap deterministic checks first across the WHOLE batch: "
        "char counts, from_value substring leaks, presence of 'je '-style.\n"
        "3. Read every line and grade tone/customer-centricity.\n"
        "4. Call write_critique once with concrete prompt-template feedback "
        "(specify offending row indices and what to add/remove from the "
        "system prompt).\n"
        "5. Call judge once. Approve ONLY when ALL hard constraints pass on "
        "ALL rows AND quality is good across the batch."
    ),
    tools=[run_eval, write_critique, judge],
    llm=ChatOpenAI(
        model=REASONING_MODEL,
        reasoning_effort="low",
        use_responses_api=True,
    ),
)


def _run_critique(outputs: List[dict]) -> dict:
    _pending_verdict.update({"critique": None, "approved": None, "reason": None})
    _banner("CRITIQUE PASS", char="-")

    # Compact view for the critic prompt: include from_* so leaks can be
    # detected, but trim verbose description fields not needed for review.
    batch_view = [
        {
            "row_index": o["row_index"],
            "consideration": o["row"]["consideration_name"],
            "from_value": o["row"]["from_value"],
            "to_value": o["row"]["to_value"],
            "to_rank": o["row"]["to_rank"],
            "is_top_tier": o["generator_input"]["is_top_tier"],
            "to_pro": o["row"]["to_pro"],
            "to_con": o["row"]["to_con"],
            "output": o["output"],
            "char_count": o["char_count"],
        }
        for o in outputs
    ]

    msg = HumanMessage(content=(
        f"Objective: {OBJECTIVE}\n\n"
        f"Batch ({len(batch_view)} rows):\n"
        f"{json.dumps(batch_view, ensure_ascii=False, indent=2)}\n\n"
        "Run evals across the batch, then call write_critique once and "
        "judge once."
    ))
    run_full_turn(critique_agent, [msg])
    return {
        "approved": bool(_pending_verdict["approved"]),
        "critique": _pending_verdict["critique"] or "(no critique written)",
        "reason": _pending_verdict["reason"] or "(no reason given)",
    }


prompt_owner = Agent(
    name="PromptOwner",
    instructions=(
        "You own a generation pipeline that produces Dutch upsell lines for "
        "Coolblue's 'green zone'. The pipeline runs your CURRENT system "
        "prompt against EVERY row in the dataset; for each row the user "
        "message is a JSON object with these fields only:\n"
        f"  {list(GENERATOR_INPUT_FIELDS) + ['is_top_tier']}\n"
        "from_* fields are intentionally withheld — your prompt must "
        "instruct the model to describe only the offered (to_value) "
        "benefit, never the previous option.\n\n"
        f"HARD CONSTRAINTS per generated line: ≤{MAX_CHARS} chars, Dutch, "
        "B1, active 'je krijgt'-style, customer-centric, no jargon, no "
        "comparative phrasing.\n\n"
        "TOOLS:\n"
        "- update_prompt(new_prompt, note): create a new versioned system "
        "prompt. Diff-like notes ('added explicit char limit', 'banned "
        "comparative phrasing', 'added top-tier tonality rule').\n"
        f"- update_model_settings: choose from {sorted(ALLOWED_GENERATION_MODELS)} "
        "+ tune temperature / max_output_tokens (keep tokens ~80–150 — "
        "single short line).\n"
        "- run_generation_pipeline: runs your current prompt against ALL "
        "rows. Returns approval, critique, char-length stats "
        "(n_over_max_chars, char range), and a sample of outputs.\n\n"
        "WORKFLOW: refine prompt -> run -> read critique + stats -> refine. "
        "Stop calling tools when the Critic approves; then summarise the "
        f"final prompt + settings. Hard cap: {MAX_ITERATIONS} iterations.\n\n"
        "TIPS: the critic reports specific offending row indices. Address "
        "them concretely in the next prompt revision (e.g. add an explicit "
        "char counter step, ban specific phrases). Do not include style "
        "examples in the prompt — the generator should learn voice from "
        "instructions only."
    ),
    tools=[update_prompt, update_model_settings, run_generation_pipeline],
    llm=ChatOpenAI(
        model=REASONING_MODEL,
        reasoning_effort="medium",
        use_responses_api=True,
    ),
)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

INITIAL_PROMPT = (
    "Je schrijft korte Nederlandse upsell-zinnen voor de Coolblue-website.\n"
    "\n"
    "De gebruikersinvoer is een JSON met de aangeboden upgrade. Lever "
    "EXACT één regel: een klantgerichte zin van maximaal 100 tekens "
    "(inclusief spaties).\n"
    "\n"
    "Regels:\n"
    "- Nederlands, B1-niveau, actief, één korte zin.\n"
    "- Begin bij voorkeur met 'Je krijgt …'.\n"
    "- Beschrijf alleen het voordeel van de aangeboden waarde (to_value).\n"
    "- Noem of vergelijk de vorige waarde NIET. Geen 'meer dan', 'in plaats "
    "van', of soortgelijke vergelijkingen.\n"
    "- Vertaal vakjargon naar herkenbare situaties voor de klant.\n"
    "- Bij is_top_tier == true: gebruik tonality van 'beste van het beste' / "
    "'nooit meer ergens over inzitten' waar dat natuurlijk past.\n"
    "- Geen titel, geen uitleg, geen aanhalingstekens — alleen de zin.\n"
)


def main() -> None:
    config.run_dir = _init_run_dir()
    _create_prompt_version(INITIAL_PROMPT, note="initial prompt")

    _banner("CRITIQUE-PATTERN ORCHESTRATION  (Coolblue upsell copy)")
    _section("setup")
    _kv("objective:", OBJECTIVE)
    _kv("dataset rows:", len(DATA))
    _kv("max chars/line:", MAX_CHARS)
    _kv("reasoning model:", REASONING_MODEL)
    _kv("allowed gen models:", sorted(ALLOWED_GENERATION_MODELS))
    _kv("initial model:", config.model)
    _kv("initial temperature:", config.temperature)
    _kv("run dir:", config.run_dir.relative_to(Path(__file__).parent))
    _kv("starting prompt:", "v001")
    print()

    messages = [HumanMessage(content=(
        "Begin. Iterate on the prompt and model settings until the Critic "
        "approves the batch. Then summarise the final prompt + settings and "
        "stop calling tools."
    ))]
    run_full_turn(prompt_owner, messages)

    _persist_manifest()
    _banner("FINAL")
    _kv("iterations run:", config.iteration)
    _kv("prompt versions:", len(config.prompt_versions))
    _kv("final prompt version:", f"v{config.current_version:03d}")
    _kv("final model:", config.model)
    _kv("final temperature:", config.temperature)
    _kv("final max_output_tokens:", config.max_output_tokens)
    _kv("run dir:", config.run_dir.relative_to(Path(__file__).parent))

    _section(f"final prompt (v{config.current_version:03d})")
    _block(config.prompt)
    if config.last_outputs:
        _section("final outputs")
        for o in config.last_outputs:
            r = o["row"]
            head = f"{r['consideration_name'][:22]:<22} {r['from_value']:>6} → {r['to_value']:<6}"
            flag = " ⚠" if o["char_count"] > MAX_CHARS else "  "
            print(f"  [{o['char_count']:3d}c{flag}] {head}: {o['output']}")


if __name__ == "__main__":
    main()
