"""Parseur de transcript Claude Code (.jsonl) → liste d'étapes plates et exactes.

Chaque étape : {i, kind, ts, text, tools:[{id,name,input}], is_error, usage, model}
kinds : prompt | assistant | thinking | tool_use | tool_result | system | other
Rien n'est interprété ici : c'est la matière brute pour metrics.py et pour les
fenêtres envoyées à JEV.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Step:
    i: int
    kind: str
    ts: str | None = None
    text: str = ""
    tools: list[dict] = field(default_factory=list)
    is_error: bool = False
    usage: dict | None = None
    model: str | None = None
    sidechain: bool = False
    raw_type: str = ""


def _blocks(m) -> list:
    if not isinstance(m, dict):
        return []
    c = m.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


def _result_text(b) -> str:
    c = b.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    return ""


def parse(path: Path) -> list[Step]:
    return parse_lines(Path(path).read_text().splitlines())


def parse_events(events: list[dict]) -> list[Step]:
    return parse_lines([json.dumps(e, ensure_ascii=False) for e in events])


def parse_lines(lines: list[str]) -> list[Step]:
    steps: list[Step] = []
    names: dict[str, str] = {}
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = o.get("type")
        st = Step(i=i, kind="other", ts=o.get("timestamp"), sidechain=bool(o.get("isSidechain")), raw_type=t or "")
        m = o.get("message")
        if t == "user":
            bs = _blocks(m)
            results = [b for b in bs if b.get("type") == "tool_result"]
            if results:
                st.kind = "tool_result"
                st.tools = [{"id": b.get("tool_use_id"), "name": names.get(b.get("tool_use_id"), "?"),
                             "is_error": bool(b.get("is_error"))} for b in results]
                st.is_error = any(x["is_error"] for x in st.tools)
                st.text = "\n\n".join(_result_text(b) for b in results)
                r = o.get("toolUseResult")
                if isinstance(r, dict):
                    st.tools[0]["duration_ms"] = r.get("durationMs")
                    if r.get("stderr"):
                        st.tools[0]["stderr"] = r.get("stderr")[:2000]
            elif o.get("isMeta") or o.get("isCompactSummary"):
                st.kind = "system"
                st.text = "\n".join(b.get("text", "") for b in bs if b.get("type") == "text")
            else:
                st.kind = "prompt"
                st.text = "\n".join(b.get("text", "") for b in bs if b.get("type") == "text")
        elif t == "assistant":
            bs = _blocks(m)
            uses = [b for b in bs if b.get("type") == "tool_use"]
            texts = [b.get("text", "") for b in bs if b.get("type") == "text"]
            thinks = [b.get("thinking", "") for b in bs if b.get("type") in ("thinking", "redacted_thinking")]
            st.model = (m or {}).get("model")
            st.usage = (m or {}).get("usage")
            for u in uses:
                names[u.get("id")] = u.get("name", "?")
            if uses:
                st.kind = "tool_use"
                st.tools = [{"id": u.get("id"), "name": u.get("name"), "input": u.get("input")} for u in uses]
                st.text = "\n".join(texts)
            elif texts:
                st.kind = "assistant"
                st.text = "\n".join(texts)
            elif thinks:
                st.kind = "thinking"
                st.text = "\n".join(thinks)
            else:
                st.kind = "assistant"
        elif t == "system":
            st.kind = "system"
            st.text = o.get("content") if isinstance(o.get("content"), str) else json.dumps(
                {k: v for k, v in o.items() if k not in ("uuid", "parentUuid", "timestamp", "sessionId", "cwd", "version")},
                ensure_ascii=False)[:2000]
        steps.append(st)
    return steps


def tool_call_signature(tool: dict) -> str:
    """Empreinte exacte d'un appel d'outil (nom + input normalisé) pour détecter les répétitions."""
    return tool.get("name", "?") + ":" + json.dumps(tool.get("input"), sort_keys=True, ensure_ascii=False)


def render(steps: list[Step], *, max_chars_per_step: int = 1500, kinds=("prompt", "assistant", "tool_use", "tool_result")) -> str:
    """Rendu texte numéroté par étape (S#), borné, pour servir de state à JEV."""
    out = []
    for s in steps:
        if s.kind not in kinds:
            continue
        head = f"[S{s.i}] {s.kind.upper()}"
        if s.kind == "tool_use":
            head += " " + ", ".join(f"{t['name']}({json.dumps(t.get('input'), ensure_ascii=False)[:300]})" for t in s.tools)
        if s.kind == "tool_result":
            head += " " + ", ".join(t["name"] + (" ERROR" if t.get("is_error") else "") for t in s.tools)
        body = s.text.strip()
        if len(body) > max_chars_per_step:
            body = body[: max_chars_per_step // 2] + f"\n…[{len(body) - max_chars_per_step} chars omis]…\n" + body[-max_chars_per_step // 2:]
        out.append(head + ("\n" + body if body else ""))
    return "\n\n".join(out)
