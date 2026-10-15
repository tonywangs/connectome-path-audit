#!/usr/bin/env python3
"""One offline verification command. --record refreshes actual evidence artifacts.

Requires the pinned verification environment and an already installed Chromium.
Never downloads packages, browsers, or data. Builds/installs locally in a fresh
venv, with internet socket use forbidden in Python child processes.
"""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import tempfile
import time
import venv

ROOT = Path(__file__).resolve().parents[1]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, cwd, env, logs, timeout=60):
    start = time.monotonic()
    # GNU time records peak RSS of the specific child, not cumulative RUSAGE_CHILDREN.
    time_bin = shutil.which('time')
    if not time_bin or platform.system() != 'Linux':
        raise RuntimeError('Verification measurements require Linux /usr/bin/time')
    with tempfile.TemporaryDirectory() as td:
        metrics = Path(td) / 'rss'
        proc = subprocess.run([time_bin, '-f', '%M', '-o', str(metrics), *map(str, command)],
                              cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=timeout, text=True)
        elapsed = time.monotonic() - start
        logs.append(proc.stdout)
        if proc.returncode:
            print(proc.stdout, file=sys.stderr)
            raise RuntimeError(f'command failed ({proc.returncode}): {command}')
        return {'elapsed_seconds': round(elapsed, 6), 'peak_process_rss_kib': int(metrics.read_text().strip())}


def fixture(directory, kind):
    directory.mkdir()
    nodes, edges = [], []
    if kind == 'browser':
        nodes = [(f'n{i:03}', 'End of chain' if i == 64 else f'Chain node {i}') for i in range(65)]
        hostile = '</script><img src="https://example.invalid/pixel" onerror="window.pwned=1">'
        nodes += [('hostile', 'Hostile ' + hostile + ' & \\u003c @@SCRIPT@@'), ('isolated', 'Isolated fixture cell')]
        edges = [(f'n{i:03}', f'n{i+1:03}', 5) for i in range(64)] + [('n000', 'hostile', 7)]
        sources = ['n000']; targets = [node for node, _ in nodes] + ['absent']; thresholds = [1, 5, 6]
    else:
        rng = random.Random(1701)
        nodes = [(f'n{i:04}', f'Seeded synthetic cell {i}') for i in range(2000)]
        edges = [(nodes[i][0], nodes[i+1][0], rng.randint(1, 20)) for i in range(len(nodes) - 1)]
        edges += [(rng.choice(nodes)[0], rng.choice(nodes)[0], rng.randint(1, 20)) for _ in range(8001)]
        sources = [n for n, _ in nodes[:8]]; targets = [n for n, _ in nodes[-32:]]; thresholds = [1, 5, 10, 15]
    with (directory / 'connections.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['source', 'target', 'synapses']); w.writerows(edges)
    with (directory / 'nodes.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['node_id', 'label']); w.writerows(nodes)
    meta = json.loads((ROOT / 'examples/provenance.json').read_text())
    meta.update(dataset=f'{kind} verification fixture', revision='seed-1701-v1' if kind == 'benchmark' else 'browser-v1',
                selection='Generated deterministically by scripts/verify.py; all edges are synthetic.',
                limitations=['Synthetic test data; no biological interpretation. Only listed edges are present.'])
    (directory / 'provenance.json').write_text(json.dumps(meta, sort_keys=True) + '\n')
    args = [str(directory / 'connections.csv'), '--nodes', str(directory / 'nodes.csv'), '--provenance', str(directory / 'provenance.json')]
    for s in sources: args += ['--source', s]
    for t in targets: args += ['--target', t]
    args += ['--thresholds', ','.join(map(str, thresholds))]
    return args


def verify_bundle(directory):
    manifest = json.loads((directory / 'COMPLETE.json').read_text())
    assert manifest['status'] == 'complete'
    for name, meta in manifest['artifacts'].items():
        assert sha(directory / name) == meta['sha256']
        assert (directory / name).stat().st_size == meta['bytes']
    return {p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in sorted(directory.iterdir())}


def check_benchmark_reference(report, inputs):
    import networkx as nx
    document = json.loads(report.read_text())
    edges = {}
    with (inputs / 'connections.csv').open() as f:
        for row in csv.DictReader(f):
            key = row['source'], row['target']
            edges[key] = edges.get(key, 0) + int(row['synapses'])
    count = 0
    for threshold in document['thresholds']:
        graph = nx.DiGraph(); graph.add_nodes_from(n['id'] for n in document['nodes'])
        graph.add_edges_from(pair for pair, total in edges.items() if total >= threshold)
        for source in sorted({q['source'] for q in document['queries']}):
            distances = nx.single_source_shortest_path_length(graph, source)
            for r in document['results']:
                if r['source'] != source or r['threshold'] != threshold: continue
                assert r['hops'] == distances.get(r['target'])
                assert r['status'] == ('reachable' if r['target'] in distances else 'no_path_in_supplied_graph')
                assert r['edge_counts'] == [edges[a, b] for a, b in zip(r['path'], r['path'][1:])]
                assert all(c >= threshold for c in r['edge_counts'])
                count += 1
    return count


def check_failure_reference(report, inputs):
    """Independent installed-artifact oracle: remove every retained pair."""
    import networkx as nx
    doc = json.loads(report.read_text())
    totals = {}
    with (inputs / 'connections.csv').open() as f:
        for row in csv.DictReader(f):
            edge = row['source'], row['target']
            totals[edge] = totals.get(edge, 0) + int(row['synapses'])
    findings = witnesses = deletions = 0
    for threshold in doc['thresholds']:
        graph = nx.DiGraph(); graph.add_nodes_from(n['id'] for n in doc['nodes'])
        graph.add_edges_from(e for e, count in totals.items() if count >= threshold)
        expected = {}
        distances = {}
        for edge in list(graph.edges):
            changed = graph.copy(); changed.remove_edge(*edge)
            distances[edge] = dict(nx.all_pairs_shortest_path_length(changed))
            deletions += 1
        for r in doc['results']:
            if r['threshold'] != threshold: continue
            f = r['single_edge_failure']; a, b = r['source'], r['target']
            findings += 1
            if a not in graph or b not in graph:
                assert f['status'] == 'missing_node'; continue
            if not nx.has_path(graph, a, b):
                assert f['status'] == 'initially_unreachable'; continue
            assert f['status'] == 'complete'
            expected = {e for e, d in distances.items() if b not in d[a]}
            assert set(map(tuple, f['critical_edges'])) == expected
            for c in f['candidates']:
                edge = tuple(c['edge'])
                assert c['synapses'] == totals[edge]
                if edge in expected:
                    assert c['status'] == 'disconnected' and c['search_complete']
                    assert c['visited_nodes'] == len(distances[edge][a])
                    continue
                assert c['status'] == 'alternative_path'
                path = c['path']
                assert path[0] == a and path[-1] == b
                assert len(path) - 1 == distances[edge][a][b]
                pairs = list(zip(path, path[1:]))
                assert edge not in pairs and all(totals.get(e, 0) >= threshold for e in pairs)
                assert c['edge_counts'] == [totals[e] for e in pairs]
                witnesses += 1
    return {'findings': findings, 'reference_removals': deletions, 'alternative_witnesses': witnesses}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true', help='refresh results/edge-failure-verification.json, results/edge-failure-tests.txt, and results/edge-failure-example/')
    args = parser.parse_args()
    required = {'networkx': '3.4.2', 'playwright': '1.51.0', 'setuptools': '75.8.0', 'wheel': '0.45.1', 'pip': '25.0.1',
                'pyee': '12.1.1', 'greenlet': '3.5.6', 'typing-extensions': '4.16.0'}
    for name, version in required.items():
        assert importlib.metadata.version(name) == version, f'{name} must be {version}'
    logs = []
    started = time.monotonic()
    evidence = {'schema': 'connectome-verification/v1', 'environment': {
        'python': sys.version, 'platform': platform.platform(), 'machine': platform.machine(),
        'dependencies': required, 'cpu_count': os.cpu_count(), 'measurement': 'GNU time maximum resident set size in KiB; elapsed includes process launch'},
        'reference': {'seed_range': [0, 299], 'graphs': 300,
                      'methods': ['NetworkX 3.4.2', 'independent Floyd-Warshall', 'distance-constrained canonical witness']}}
    import networkx.algorithms.shortest_paths.unweighted as reference
    evidence['reference']['unweighted_source_sha256'] = sha(reference.__file__)
    with tempfile.TemporaryDirectory(prefix='connectome-verify-') as td:
        temp = Path(td); guard = temp / 'guard'; guard.mkdir()
        # Child processes including installed CLI and pip cannot use network sockets.
        attempts = temp / 'network-attempts'
        (guard / 'sitecustomize.py').write_text('''import socket, os
from pathlib import Path
def denied(*a, **kw):
 Path(os.environ["AUDIT_NETWORK_ATTEMPTS"]).write_text("Network attempted")
 raise RuntimeError("Network forbidden during offline verification")
socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
socket.getaddrinfo = denied
''')
        env = {**os.environ, 'PYTHONPATH': str(guard), 'PIP_NO_INDEX': '1', 'PIP_DISABLE_PIP_VERSION_CHECK': '1',
               'PIP_CONFIG_FILE': os.devnull, 'PIP_NO_CACHE_DIR': '1', 'AUDIT_NETWORK_ATTEMPTS': str(attempts),
               'PYTHONHASHSEED': '1'}
        test_env = {**env, 'PYTHONPATH': os.pathsep.join([str(guard), str(ROOT / 'src')])}
        evidence['unit_tests'] = run([sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'), '-v'], temp, test_env, logs)
        # Derive, rather than invent, randomized coverage counts from test output.
        import re
        match = re.search(r'Independent reference: (\d+) seeds, (\d+) findings, (\d+) verified witnesses', logs[-1])
        assert match
        evidence['reference'].update(graphs=int(match[1]), findings=int(match[2]), witnesses=int(match[3]))
        edge_match = re.search(r'Edge failure reference: (\d+) seeds, (\d+) findings, (\d+) full-edge reference removals, (\d+) alternative witnesses, (\d+) critical findings', logs[-1])
        assert edge_match
        evidence['edge_failure_reference'] = dict(zip(['graphs', 'findings', 'reference_removals', 'alternative_witnesses', 'critical_findings'], map(int, edge_match.groups())))
        match = re.search(r'Ran (\d+) tests', logs[-1]); assert match
        evidence['unit_tests']['tests_passed'] = int(match[1])
        # Build from a clean source copy. No source-tree import in installed runs.
        build_src = temp / 'source'; build_src.mkdir()
        shutil.copytree(ROOT / 'src', build_src / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.egg-info'))
        shutil.copy2(ROOT / 'pyproject.toml', build_src)
        wheel_dir = temp / 'wheels'; wheel_dir.mkdir()
        evidence['build'] = run([sys.executable, '-m', 'pip', 'wheel', '--no-index', '--no-deps', '--no-build-isolation',
                                 '--wheel-dir', wheel_dir, build_src], temp, env, logs)
        isolated = temp / 'installed'; venv.EnvBuilder(with_pip=False).create(isolated)
        wheel = next(wheel_dir.glob('*.whl'))
        evidence['install'] = run([sys.executable, '-m', 'pip', '--python', isolated / 'bin/python', 'install',
                                   '--no-index', '--no-deps', wheel], temp, env, logs)
        run([isolated / 'bin/python', '-c', 'import connectome_audit; assert "installed" in connectome_audit.__file__; print(connectome_audit.__file__)'], temp, env, logs)
        executable = isolated / 'bin/connectome-audit'
        example_args = [ROOT / 'examples/connections.csv', '--nodes', ROOT / 'examples/nodes.csv',
                        '--provenance', ROOT / 'examples/provenance.json', '--source', 'sensor', '--target', 'motor',
                        '--target', 'isolated', '--target', 'sensor', '--target', 'absent', '--thresholds', '1,5,6,9,10']
        example_hashes = {p.name: sha(p) for p in (ROOT / 'examples').iterdir() if p.is_file()}
        example = temp / 'example'
        evidence['installed_example'] = run([executable, *example_args, '--output', example], temp, env, logs)
        evidence['installed_example']['artifacts'] = verify_bundle(example)
        report = json.loads((example / 'report.json').read_text())
        assert [r['hops'] for r in report['results'] if r['target'] == 'motor'] == [2, 2, 3, 3, None]
        assert example_hashes == {p.name: sha(p) for p in (ROOT / 'examples').iterdir() if p.is_file()}
        evidence['installed_example']['unchanged_input_hashes'] = example_hashes
        again = temp / 'example-again'
        run([executable, *example_args, '--output', again], temp, {**env, 'PYTHONHASHSEED': '73'}, logs)
        assert verify_bundle(again) == verify_bundle(example)
        evidence['installed_example']['byte_identical_repeated_outputs'] = True
        inputs = temp / 'benchmark-inputs'; bench_args = fixture(inputs, 'benchmark')
        before = {p.name: sha(p) for p in inputs.iterdir()}
        benchmark = temp / 'benchmark'
        evidence['benchmark'] = run([executable, *bench_args, '--output', benchmark], temp, env, logs)
        second = temp / 'benchmark-again'
        evidence['benchmark']['repeat_measurement'] = run([executable, *bench_args, '--output', second], temp,
                                                         {**env, 'PYTHONHASHSEED': '73'}, logs)
        assert verify_bundle(benchmark) == verify_bundle(second)
        assert before == {p.name: sha(p) for p in inputs.iterdir()}
        evidence['benchmark'].update(seed=1701, node_count=2000, connection_rows=10000, query_pairs=256, thresholds=[1, 5, 10, 15],
                                     unchanged_input_hashes=before, byte_identical_repeated_outputs=True,
                                     artifacts=verify_bundle(benchmark),
                                     independent_findings_checked=check_benchmark_reference(benchmark / 'report.json', inputs))
        browser_inputs = temp / 'browser-inputs'; browser_args = fixture(browser_inputs, 'browser')
        browser_bundle = temp / 'browser'
        run([executable, *browser_args, '--output', browser_bundle], temp, env, logs)
        from browser_check import check
        evidence['browser'] = check(browser_bundle / 'report.html')
        # Same installed binary, now with the optional failure analysis enabled.
        failure_example = temp / 'failure-example'
        evidence['failure_example'] = run([executable, *example_args, '--single-edge-failure', '--output', failure_example], temp, env, logs)
        evidence['failure_example']['artifacts'] = verify_bundle(failure_example)
        evidence['failure_example']['reference'] = check_failure_reference(failure_example / 'report.json', ROOT / 'examples')
        failure_again = temp / 'failure-again'
        run([executable, *example_args, '--single-edge-failure', '--output', failure_again], temp,
            {**env, 'PYTHONHASHSEED': '73'}, logs)
        assert verify_bundle(failure_example) == verify_bundle(failure_again)
        evidence['failure_example']['byte_identical_repeated_outputs'] = True
        assert example_hashes == {p.name: sha(p) for p in (ROOT / 'examples').iterdir() if p.is_file()}
        evidence['failure_example']['unchanged_input_hashes'] = example_hashes
        failure_data = json.loads((failure_example / 'report.json').read_text())
        assert failure_data['single_edge_failure']['status'] == 'complete'
        # A long detour replaces the first chain edge; later edges remain critical.
        with (browser_inputs / 'nodes.csv').open('a', newline='') as f:
            csv.writer(f).writerows((f'alt{i:03}', '') for i in range(25))
        with (browser_inputs / 'connections.csv').open('a', newline='') as f:
            csv.writer(f).writerows([('n000', 'alt000', 5)] +
                [(f'alt{i:03}', f'alt{i+1:03}', 5) for i in range(24)] + [('alt024', 'n001', 5)])
        before_failure = {p.name: sha(p) for p in browser_inputs.iterdir()}
        failure_browser = temp / 'failure-browser'
        evidence['failure_workload'] = run([executable, *browser_args, '--single-edge-failure', '--output', failure_browser], temp, env, logs)
        evidence['failure_workload']['artifacts'] = verify_bundle(failure_browser)
        failure_doc = json.loads((failure_browser / 'report.json').read_text())
        evidence['failure_workload'].update(graph=failure_doc['graph'], queries=len(failure_doc['queries']),
            thresholds=failure_doc['thresholds'], analysis=failure_doc['single_edge_failure'])
        assert before_failure == {p.name: sha(p) for p in browser_inputs.iterdir()}
        evidence['failure_workload']['unchanged_input_hashes'] = before_failure
        evidence['failure_workload']['reference'] = check_failure_reference(failure_browser / 'report.json', browser_inputs)
        failure_repeat = temp / 'failure-browser-repeat'
        run([executable, *browser_args, '--single-edge-failure', '--output', failure_repeat], temp,
            {**env, 'PYTHONHASHSEED': '73'}, logs)
        assert verify_bundle(failure_repeat) == verify_bundle(failure_browser)
        evidence['failure_workload']['byte_identical_repeated_outputs'] = True
        evidence['failure_browser'] = check(failure_browser / 'report.html')
        partial = temp / 'partial'
        run([executable, *example_args, '--single-edge-failure', '--max-candidate-removals', '1', '--output', partial], temp, env, logs)
        assert json.loads((partial / 'report.json').read_text())['single_edge_failure']['status'] == 'partial'
        from browser_check import check_partial
        evidence['partial_browser'] = check_partial(partial / 'report.html')
        assert not attempts.exists(), 'offline Python process attempted network access'
        evidence['python_network_attempts'] = 0
        evidence['total_elapsed_seconds'] = round(time.monotonic() - started, 6)
        # Include only source inputs, not generated evidence, in the verification fingerprint.
        paths = [ROOT / 'pyproject.toml', ROOT / 'requirements-verify.txt']
        for directory in ['src', 'scripts', 'tests', 'examples']:
            paths += [p for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and not any(x.endswith('.egg-info') for x in p.parts)]
        evidence['verified_files'] = {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)}
        if args.record:
            results = ROOT / 'results'; results.mkdir(exist_ok=True)
            (results / 'edge-failure-verification.json').write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
            (results / 'edge-failure-tests.txt').write_text(logs[0])
            target = results / 'edge-failure-example'; target.mkdir(exist_ok=True)
            for name in ['report.html', 'report.json', 'COMPLETE.json']: shutil.copy2(failure_example / name, target / name)
        print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__': raise SystemExit(main())
