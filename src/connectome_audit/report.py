"""Deterministic bounded serialization and transactional local report bundles."""
from dataclasses import asdict
import base64
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path

from . import __version__
from .core import LimitError

INTERPRETATION = [
    "A missing path means no directed path in the supplied graph at this threshold, not biological disconnection.",
    "Sampling boundaries, omitted neurons or connections, proofreading errors, and upstream filters can remove real pathways. Lowering a threshold cannot restore omitted data.",
    "Synapse counts gate edges; shortest means fewest hops, not strongest or most likely transmission. One deterministic witness is shown, not every possible path.",
    "Wiring paths do not establish signal propagation, causal influence, engineered dynamics, or consciousness. No physiological or clinical validation is claimed.",
    "Source equals target has a zero-hop path when the ID is present; missing IDs are unresolved, including missing self-queries.",
]


def make_document(graph, analysis, budget):
    return {"schema": "connectome-audit/v1", "tool_version": __version__, "status": "complete",
            "input_contract": "connectome-csv/v1", "inputs": graph.inputs,
            "provenance": graph.provenance, "interpretation": INTERPRETATION,
            "semantics": {"direction": "source to target", "threshold": "aggregated synapses >= threshold",
                          "duplicates": "sum before thresholding", "self_loops": "retained",
                          "tie_break": "Unicode-code-point lexicographic shortest node sequence",
                          "source_equals_target": "zero hops when present", "distance": "unweighted hops"},
            "graph": {"node_count": len(graph.nodes), "edge_count": len(graph.edges),
                      "connection_rows": graph.rows, "duplicate_rows": graph.duplicate_rows,
                      "self_loop_edges": graph.self_loop_edges},
            "nodes": [{"id": n, "label": graph.nodes[n]} for n in sorted(graph.nodes)],
            "limits": asdict(budget.limits),
            "work": {"operations": budget.operations, "witness_nodes": budget.witness_nodes},
            **analysis}


def canonical_json(document, budget):
    parts, size = [], 0
    encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
    for part in encoder.iterencode(document):
        budget.check()
        part = part.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        size += len(part)  # ensure_ascii means one ASCII character = one byte
        if size + 1 > budget.limits.report_bytes:
            raise LimitError("JSON report byte limit exhausted")
        parts.append(part)
    return ("".join(parts) + "\n").encode("ascii")


def html_report(json_bytes, budget):
    resources = files("connectome_audit")
    css = resources.joinpath("report.css").read_text(encoding="utf-8")
    js = resources.joinpath("report.js").read_text(encoding="utf-8")
    template = resources.joinpath("report.html").read_text(encoding="utf-8")
    def sha(text):
        return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()
    # Escaping '<' prevents termination of the inert JSON script by hostile labels.
    data = json_bytes.decode("ascii").replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    replacements = {"@@CSP@@": f"default-src 'none'; script-src 'sha256-{sha(js)}'; style-src 'sha256-{sha(css)}'; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'",
                    "@@STYLE@@": css, "@@DATA@@": data, "@@SCRIPT@@": js}
    # Single substitution pass prevents values containing template tokens from
    # being interpreted as instructions or replaced later.
    import re
    html = re.sub(r"@@(?:CSP|STYLE|DATA|SCRIPT)@@", lambda m: replacements[m[0]], template).encode()
    if len(html) > budget.limits.report_bytes:
        raise LimitError("HTML report byte limit exhausted")
    budget.check()
    return html


def write_bundle(output, json_bytes, html_bytes, budget):
    """Never overwrite. COMPLETE.json is the last commit marker.

    All normal exceptions including cancellation remove only files created here.
    SIGKILL/power loss can leave an uncommitted directory; consumers must require
    COMPLETE.json. Files are fsynced before the marker; not a durable database.
    """
    output = Path(output)
    output.mkdir()  # atomic exclusive reservation, including empty existing dirs
    created = []
    try:
        artifacts = {"report.json": json_bytes, "report.html": html_bytes}
        manifest = {"schema": "connectome-bundle/v1", "status": "complete", "artifacts": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for name, data in artifacts.items()}}
        artifacts["COMPLETE.json"] = canonical_json(manifest, budget)
        for name, data in artifacts.items():
            budget.check()
            path = output / name
            # Exclusive creation also avoids following an injected symlink.
            with path.open("xb") as stream:
                created.append(path)
                for start in range(0, len(data), 65536):
                    budget.check()
                    stream.write(data[start:start + 65536])
                stream.flush()
                os.fsync(stream.fileno())
        budget.check()
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        output.rmdir()
        raise
