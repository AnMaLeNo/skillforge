"""Signaux exacts calculés par le code (jamais par JEV) sur un épisode."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .transcript import Step, parse, tool_call_signature

DONE_RE = re.compile(r"\b(done|complete[d]?|finished|terminé|fini|c'est fait|implemented|all set)\b", re.I)
VERIFY_TOOLS = {"Bash"}


def compute(ep_dir: Path) -> dict:
    ep_dir = Path(ep_dir)
    meta = json.loads((ep_dir / "meta.json").read_text())
    tpath = ep_dir / "transcript.jsonl"
    steps: list[Step] = parse(tpath) if tpath.exists() else []
    main = [s for s in steps if not s.sidechain]
    tool_uses = [t for s in main if s.kind == "tool_use" for t in s.tools]
    results = [t for s in main if s.kind == "tool_result" for t in s.tools]
    sigs = Counter(tool_call_signature(t) for t in tool_uses)
    repeated = {k: v for k, v in sigs.items() if v >= 2}
    err_results = [t for t in results if t.get("is_error")]
    err_sigs = Counter()
    # erreurs répétées sur le même appel : on relie result→use par id
    use_by_id = {t["id"]: t for t in tool_uses}
    for t in err_results:
        u = use_by_id.get(t["id"])
        if u:
            err_sigs[tool_call_signature(u)] += 1
    usage_in = usage_out = cache_read = 0
    for s in main:
        if s.usage:
            usage_in += s.usage.get("input_tokens", 0) or 0
            usage_out += s.usage.get("output_tokens", 0) or 0
            cache_read += s.usage.get("cache_read_input_tokens", 0) or 0
    assistant_texts = [s for s in main if s.kind == "assistant" and s.text.strip()]
    final_text = assistant_texts[-1].text if assistant_texts else (meta.get("result_text") or "")
    last_verify_i = max([s.i for s in main if s.kind == "tool_use" and any(t["name"] in VERIFY_TOOLS for t in s.tools)], default=-1)
    last_write_i = max([s.i for s in main if s.kind == "tool_use" and any(t["name"] in ("Write", "Edit", "MultiEdit", "NotebookEdit") for t in s.tools)], default=-1)
    tool_names = Counter(t["name"] for t in tool_uses)
    c = meta.get("claude") or {}
    return {
        "episode_id": meta["episode_id"], "skill": meta["skill"], "task": meta["task"],
        "rc": meta["rc"], "timed_out": meta["timed_out"], "wall_ms": meta["wall_ms"],
        "is_error": c.get("is_error"), "subtype": c.get("subtype"), "stop_reason": c.get("stop_reason"),
        "num_turns": c.get("num_turns"), "cost_usd": c.get("total_cost_usd"), "api_ms": c.get("duration_api_ms"),
        "steps": len(main), "assistant_msgs": sum(1 for s in main if s.kind in ("assistant", "tool_use")),
        "tool_calls": len(tool_uses), "tool_names": dict(tool_names),
        "tool_errors": len(err_results),
        "repeated_identical_calls": sum(v - 1 for v in repeated.values()), "max_repeat": max(repeated.values(), default=1),
        "repeated_failing_calls": {k[:120]: v for k, v in err_sigs.items() if v >= 2},
        "tokens_in": usage_in, "tokens_out": usage_out, "cache_read": cache_read,
        "files_written": len(meta.get("files_after") or {}), "files_after": sorted((meta.get("files_after") or {}).keys()),
        "claims_done": bool(DONE_RE.search(final_text or "")),
        "verified_after_last_write": last_verify_i > last_write_i if last_write_i >= 0 else None,
        "final_text": (final_text or "")[:1500],
    }


if __name__ == "__main__":
    import sys
    for d in sys.argv[1:]:
        print(json.dumps(compute(Path(d)), indent=1, ensure_ascii=False))
