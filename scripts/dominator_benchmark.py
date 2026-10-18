#!/usr/bin/env python3
"""Frozen synthetic suite; isolated balanced paired extension measurements."""
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'benchmarks/dominator-suite.json'


def fixture(case, seed):
    from connectome_audit.ingest import Graph
    rng = random.Random(seed)
    n = case['nodes']; ids = [f'n{i:04}' for i in range(n)]
    edges = {(ids[i], ids[i+1]): 5 for i in range(n-1)}
    if case['kind'] == 'dense':
        edges.update({(a, b): rng.randint(1, 9) for a in ids for b in ids if rng.random() < .35})
    if case['kind'] == 'random':
        edges.update({(rng.choice(ids), rng.choice(ids)): rng.randint(1, 9) for _ in range(4*n)})
    if case['kind'] == 'diamonds':
        edges = {}
        for i in range(0, n-3, 3):
            for a, b in [(i,i+1),(i,i+2),(i+1,i+3),(i+2,i+3),(i+3,i)]:
                edges[ids[a],ids[b]] = 5
    return Graph(dict.fromkeys(ids, ''), edges, len(edges), 0,
                 sum(a == b for a,b in edges), {}, {}), [ids[0]], ids[-case['targets']:]


def worker(case, seed, method, thresholds):
    from connectome_audit.core import Budget, Limits, LimitError, analyze
    from connectome_audit.dominators import analyze_dominators
    from connectome_audit.node_failures import analyze_node_failures
    graph, sources, targets = fixture(case, seed)
    limit = case.get('operation_limit', 2_000_000)
    budget = Budget(replace(Limits(), removal_operations=limit, dominator_operations=limit))
    baseline = analyze(graph, sources, targets, thresholds, budget)
    start_operations = budget.operations
    start = time.perf_counter()
    failure = None
    failed_counts = {}
    try:
        if method == 'removal': analyze_node_failures(graph, baseline, budget)
        else: analyze_dominators(graph, baseline, budget, witnesses=method == 'dominator-witnesses')
    except LimitError as exc:
        failure = str(exc)
        # Counters in the unwound analyzer frame are diagnostic work only, never
        # partially committed classifications. No profiler affects timed success.
        tb = exc.__traceback__
        while tb:
            name, local = tb.tb_frame.f_code.co_name, tb.tb_frame.f_locals
            if name == 'analyze_node_failures':
                failed_counts = {'traversal_operations': local['work']}
            elif name == 'analyze_dominators':
                failed_counts = {'traversal_operations': local['work'].total,
                                 'witness_operations': local['witness_work']}
            tb = tb.tb_next
    elapsed = time.perf_counter()-start
    field = 'single_node_failure' if method == 'removal' else 'dominator_node_failure'
    records = []
    for r in baseline['results']:
        candidates = ([{'node':n, 'status':'unresolved'} for n in r['path'][1:-1]] if failure else r[field]['candidates'])
        for c in candidates:
            status = {'disconnected':'critical', 'alternative_path':'noncritical'}.get(c['status'], c['status'])
            records.append([r['source'], r['target'], r['threshold'], c['node'], status])
    meta = failed_counts if failure else baseline[field]
    return {'elapsed_seconds': elapsed, 'run_status': 'hard_limit' if failure else meta['status'],
            'failure': failure, 'charged_extension_operations': budget.operations-start_operations,
            'traversal_operations': meta.get('traversal_operations'),
            'witness_operations': meta.get('witness_operations'),
            'completed_classifications': sum(r[-1] != 'unresolved' for r in records),
            'unresolved_classifications': sum(r[-1] == 'unresolved' for r in records),
            'witness_status': 'unreported_hard_limit' if failure else meta.get('witness_status', 'included_in_removal_search'),
            'records': records}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--worker'); p.add_argument('--method'); p.add_argument('--output'); args=p.parse_args()
    spec = json.loads(SPEC.read_text())
    if args.worker:
        case = next(c for c in spec['cases'] if c['name'] == args.worker)
        print(json.dumps(worker(case, spec['seed'], args.method, spec['thresholds']), sort_keys=True)); return
    evidence = {'suite_sha256': hashlib.sha256(SPEC.read_bytes()).hexdigest(),
                'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'measurement': spec['comparison'], 'cases': []}
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join(filter(None, [str(ROOT/'src'), os.environ.get('PYTHONPATH')]))}
    for case in spec['cases']:
        runs = []
        for repeat in range(spec['paired_repetitions']):
            methods = ['removal', 'dominator', 'dominator-witnesses']
            if repeat % 2: methods.reverse()
            pair = {}
            with tempfile.TemporaryDirectory() as td:
                for method in methods:
                    rss = Path(td)/'rss'
                    proc = subprocess.run(['/usr/bin/time','-f','%M','-o',str(rss),sys.executable,__file__,
                                           '--worker',case['name'],'--method',method],
                                          env=env, capture_output=True, text=True, timeout=60, check=True)
                    pair[method] = json.loads(proc.stdout)
                    pair[method]['peak_process_rss_kib'] = int(rss.read_text())
            reference = pair['removal']['records']
            for method in ['dominator', 'dominator-witnesses']:
                candidate = pair[method]['records']
                assert [r[:-1] for r in reference] == [r[:-1] for r in candidate]
                comparable = [(a,b) for a,b in zip(reference,candidate) if a[-1] != 'unresolved' and b[-1] != 'unresolved']
                assert all(a == b for a,b in comparable)
                pair[method]['agreed_completed_classifications'] = len(comparable)
                pair[method]['exact_output_agreement'] = reference == candidate
            for value in pair.values():
                value['classification_sha256'] = hashlib.sha256(json.dumps(value.pop('records'), sort_keys=True).encode()).hexdigest()
            runs.append({'repeat': repeat, 'order': methods, 'methods': pair})
        summary = {m: {'median_seconds': statistics.median(r['methods'][m]['elapsed_seconds'] for r in runs),
                       'median_peak_rss_kib': statistics.median(r['methods'][m]['peak_process_rss_kib'] for r in runs)} for m in methods}
        evidence['cases'].append({'name':case['name'], 'summary':summary, 'runs':runs})
    raw = json.dumps(evidence, indent=2, sort_keys=True)+'\n'
    if args.output: Path(args.output).write_text(raw)
    else: print(raw)


if __name__ == '__main__': main()
