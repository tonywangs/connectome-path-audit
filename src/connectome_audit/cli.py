"""Command-line entry point. Only local files; no sockets or telemetry."""
import argparse
from dataclasses import asdict
import signal
import sys

from . import __version__
from .core import AuditError, Budget, LimitError, Limits, analyze
from .ingest import load_graph
from .report import canonical_json, html_report, make_document, write_bundle


def parser():
    p = argparse.ArgumentParser(description="Audit directed pathway sensitivity in local connectivity CSVs.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("connections", help="UTF-8 CSV: source,target,synapses")
    p.add_argument("--nodes", help="optional CSV: node_id,label (adds isolated nodes)")
    p.add_argument("--provenance", required=True, help="connectome-provenance/v1 JSON")
    p.add_argument("--source", action="append", required=True, help="exact source ID; repeat for multiple sources")
    p.add_argument("--target", action="append", required=True, help="exact target ID; repeat for multiple targets")
    p.add_argument("--thresholds", required=True, help="1..12 comma-separated positive integers")
    p.add_argument("--output", required=True, help="new output directory; parent must exist")
    for name, default in asdict(Limits()).items():
        p.add_argument("--max-" + name.replace("_", "-"), dest="limit_" + name,
                       type=float if name == "seconds" else int, default=default,
                       help=f"lower resource ceiling (default and maximum: {default})")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    old_handlers = {}
    timer = False
    try:
        limits = Limits(**{name: getattr(args, "limit_" + name) for name in asdict(Limits())})
        budget = Budget(limits)
        def interrupt(signum, frame):
            raise KeyboardInterrupt
        def timeout(signum, frame):
            raise LimitError("runtime limit exhausted")
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, interrupt)
        if hasattr(signal, "setitimer"):
            old_handlers[signal.SIGALRM] = signal.signal(signal.SIGALRM, timeout)
            signal.setitimer(signal.ITIMER_REAL, limits.seconds)
            timer = True
        pieces = args.thresholds.split(",")
        if len(pieces) > 12 or any(not s.isascii() or not s.isdecimal() or len(s) > 16 for s in pieces):
            raise AuditError("thresholds must be 1..12 comma-separated positive integers")
        thresholds = [int(s) for s in pieces]
        # Validate query size before input work; analyze validates full semantics.
        if len(set(args.source)) * len(set(args.target)) > limits.queries:
            raise LimitError("query pair limit exhausted")
        graph = load_graph(args.connections, args.nodes, args.provenance, budget)
        analysis = analyze(graph, args.source, args.target, thresholds, budget)
        document = make_document(graph, analysis, budget)
        json_bytes = canonical_json(document, budget)
        html_bytes = html_report(json_bytes, budget)
        write_bundle(args.output, json_bytes, html_bytes, budget)
        print(f"Complete: {args.output}/report.html ({len(analysis['results'])} findings)")
        return 0
    except KeyboardInterrupt:
        print("INCOMPLETE: cancelled; no completed report produced", file=sys.stderr)
        return 130
    except (AuditError, OSError, ValueError, TypeError, RecursionError, MemoryError) as exc:
        print(f"INCOMPLETE: {exc}; no completed report produced", file=sys.stderr)
        return 2
    finally:
        if timer:
            signal.setitimer(signal.ITIMER_REAL, 0)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
