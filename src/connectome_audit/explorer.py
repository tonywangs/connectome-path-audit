"""Build a bounded, self-contained interactive graph experiment from local CSVs."""
import argparse
import base64
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import re
import sys

from .core import AuditError, Budget, Limits
from .ingest import load_graph
from .report import canonical_json, write_bundle

# Keep interactive searches small enough for a synchronous offline browser UI.
EXPLORER_NODES = 2000
EXPLORER_EDGES = 50000


def make_explorer(graph, source, target):
    if len(graph.nodes) > EXPLORER_NODES or len(graph.edges) > EXPLORER_EDGES:
        raise AuditError('Explorer supports at most 2000 nodes and 50000 directed edges')
    if source not in graph.nodes or target not in graph.nodes:
        raise AuditError('Initial source and target must be present neuron IDs')
    return {
        'schema': 'connectome-explorer/v1', 'inputs': graph.inputs,
        'provenance': graph.provenance,
        'nodes': [{'id': n, 'label': label} for n, label in sorted(graph.nodes.items())],
        'edges': [[a, b, w] for (a, b), w in sorted(graph.edges.items())],
        'initial': {'source': source, 'target': target, 'threshold': 1},
        'semantics': {'direction': 'source to target', 'threshold': 'aggregated synapses >= threshold',
                      'distance': 'unweighted hops', 'tie_break': 'Unicode-code-point lexicographic shortest node sequence',
                      'removal': 'simultaneous selected intermediate nodes and all incident edges; endpoints excluded',
                      'identity': 'zero hops for a present source equal to target'},
        'limits': {'nodes': EXPLORER_NODES, 'edges': EXPLORER_EDGES},
    }


def render(document, budget):
    raw = canonical_json(document, budget)
    resources = files('connectome_audit')
    js = resources.joinpath('explorer.js').read_text()
    css = resources.joinpath('explorer.css').read_text()
    template = resources.joinpath('explorer.html').read_text()
    def sha(s):
        return base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()
    values = {
        '@@DATA@@': raw.decode('ascii'), '@@SCRIPT@@': js, '@@STYLE@@': css,
        '@@CSP@@': f"default-src 'none'; script-src 'sha256-{sha(js)}'; style-src 'sha256-{sha(css)}'; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'",
    }
    html = re.sub(r'@@(?:DATA|SCRIPT|STYLE|CSP)@@', lambda m: values[m[0]], template).encode()
    if len(html) > budget.limits.report_bytes:
        raise AuditError('Explorer HTML byte limit exceeded')
    return raw, html


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('connections', type=Path)
    parser.add_argument('--nodes', type=Path, required=True)
    parser.add_argument('--provenance', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        budget = Budget(Limits())
        graph = load_graph(args.connections, args.nodes, args.provenance, budget)
        document = make_explorer(graph, args.source, args.target)
        raw, html = render(document, budget)
        write_bundle(args.output, raw, html, budget)
        print(json.dumps({'output': str(args.output), 'nodes': len(graph.nodes), 'edges': len(graph.edges)}))
    except (AuditError, OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
