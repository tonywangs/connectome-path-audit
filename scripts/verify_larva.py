#!/usr/bin/env python3
"""Offline real-data extraction, Python audit and browser checks against raw-source NetworkX."""
import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import zipfile

import networkx as nx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '10673895'
TARGET = '10163418'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def run(args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
    result = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(f'{args}: {result.stdout}\n{result.stderr}')


def raw_reference():
    # Deliberately do not import the importer, Graph, BFS, or browser algorithms.
    archive = ROOT / 'examples/larva/upstream/elife-83739-fig1-data1-v2.zip'
    assert sha(archive.read_bytes()) == 'c92177b4720d86b210ea44c10b9354fdf079c8cca88f0c0bce3b57815293c9cb'
    with zipfile.ZipFile(archive) as z:
        meta = list(csv.DictReader(io.StringIO(z.read('elife/meta_data.csv').decode())))
        selected = {r['']: r for r in meta if r['simple_group'] in ('KCs', 'MBONs', 'MBINs', 'MB-FBNs')}
        graph = nx.DiGraph()
        graph.add_nodes_from(selected)
        for line in z.read('elife/G_edgelist.txt').decode().splitlines():
            a, b, w = line.split()
            if a in selected and b in selected:
                value = Decimal(w)
                assert value == int(value)
                assert not graph.has_edge(a, b)
                graph.add_edge(a, b, weight=int(value))
    with (ROOT / 'examples/larva/connections.csv').open() as stream:
        actual = {(r['source'], r['target']): int(r['synapses']) for r in csv.DictReader(stream)}
    assert actual == {(a, b): w['weight'] for a, b, w in graph.edges(data=True)}
    with (ROOT / 'examples/larva/nodes.csv').open() as stream:
        nodes = {r['node_id']: r['label'] for r in csv.DictReader(stream)}
    assert nodes == {n: f"{r['name']} | {r['simple_group']} | {r['hemisphere']}" for n, r in selected.items()}
    manifest = json.loads((ROOT / 'examples/larva/source-manifest.json').read_text())
    for name, info in manifest['output_files'].items():
        raw = (ROOT / 'examples/larva' / name).read_bytes()
        assert sha(raw) == info['sha256'] and len(raw) == info['bytes']
    return graph


def filtered(graph, threshold, removed=()):
    g = nx.DiGraph()
    g.add_nodes_from(n for n in graph if n not in removed)
    g.add_edges_from((a, b, attrs) for a, b, attrs in graph.edges(data=True)
                     if attrs['weight'] >= threshold and a not in removed and b not in removed)
    return g


def check_path(graph, source, target, result):
    distance = nx.shortest_path_length(graph, source, target) if nx.has_path(graph, source, target) else None
    assert result['hops'] == distance, (source, target, result, distance)
    if distance is None:
        assert result['status'] == 'unreachable' and result['nodes'] == [] and result['edges'] == []
        return
    assert result['status'] == 'reachable'
    nodes = result['nodes']
    assert nodes[0] == source and nodes[-1] == target and len(nodes) == distance + 1
    assert len(set(nodes)) == len(nodes)
    assert len(result['edges']) == distance
    for a, b, edge in zip(nodes, nodes[1:], result['edges']):
        assert edge == {'source': a, 'target': b, 'synapses': graph[a][b]['weight']}


def check_cli(graph):
    doc = json.loads((ROOT / 'results/larva-audit/report.json').read_text())
    count = 0
    for row in doc['results']:
        g = filtered(graph, row['threshold'])
        def witness(status, nodes, counts):
            assert status == ('reachable' if nodes else 'no_path_in_supplied_graph')
            return {'status': 'reachable' if nodes else 'unreachable', 'hops': len(nodes) - 1 if nodes else None, 'nodes': nodes,
                    'edges': [{'source': a, 'target': b, 'synapses': w} for a, b, w in zip(nodes, nodes[1:], counts)]}
        check_path(g, row['source'], row['target'], witness(row['status'], row['path'], row['edge_counts']))
        count += 1
        for candidate in row['single_node_failure']['candidates']:
            trial = g.copy(); trial.remove_node(candidate['node'])
            exists = nx.has_path(trial, row['source'], row['target'])
            assert candidate['status'] == ('alternative_path' if exists else 'disconnected')
            if exists:
                check_path(trial, row['source'], row['target'], witness('reachable', candidate['path'], candidate['edge_counts']))
            count += 1
    assert doc['single_node_failure']['status'] == 'complete'
    return count


def download(page, directory):
    with page.expect_download() as event:
        page.locator('#download').click()
    path = directory / 'experiment.json'
    event.value.save_as(path)
    return json.loads(path.read_text())


def verify_browser(graph, directory, record):
    counters = {'experiments': 0, 'independent_path_checks': 0}
    examples = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': 1440, 'height': 1200}, offline=True, accept_downloads=True)
        page = context.new_page()
        errors, external = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: external.append(r.url) if r.url.startswith(('http:', 'https:')) else None)
        page.goto((ROOT / 'results/larva-demo/report.html').as_uri())
        assert page.locator('#load-status').is_hidden()
        assert page.locator('#source option').count() == 408
        assert page.locator('#baseline-status').inner_text() == '2 hops'
        if record:
            page.screenshot(path=str(ROOT / 'docs/larva-demo.png'), full_page=True)
        def validate(s, t, threshold, removals):
            data = download(page, directory)
            assert (data['source'], data['target'], data['threshold'], set(data['removed'])) == (s, t, threshold, set(removals))
            for result, excluded in [(data['baseline'], ()), (data['after'], removals)]:
                check_path(filtered(graph, threshold, excluded), s, t, result)
                counters['independent_path_checks'] += 1
            for row in data['comparisons']:
                for key, excluded in [('baseline', ()), ('after', removals)]:
                    check_path(filtered(graph, row['threshold'], excluded), s, t, row[key])
                    counters['independent_path_checks'] += 1
            for prefix, result in [('baseline', data['baseline']), ('after', data['after'])]:
                status = 'No path in supplied graph' if result['hops'] is None else f"{result['hops']} hop" + ('' if result['hops'] == 1 else 's')
                assert page.locator('#' + prefix + '-status').inner_text() == status
                assert page.locator('#' + prefix + '-graph svg g .node-title').all_text_contents() == result['nodes']
                assert page.locator('#' + prefix + '-steps li').count() == len(result['nodes'])
            assert data['inputs'] == json.loads((ROOT / 'results/larva-demo/report.json').read_text())['inputs']
            counters['experiments'] += 1
            return data
        for cutoff in [1, 3, 5, 10, 20]:
            page.locator('#threshold').fill(str(cutoff))
            data = validate(SOURCE, TARGET, cutoff, [])
            examples.append({'threshold': cutoff, 'baseline_hops': data['baseline']['hops'], 'path': data['baseline']['nodes']})
        page.get_by_role('button', name='Use cutoff 10', exact=True).click()
        # Longer alternative; then two simultaneous removals; restore via individual chip.
        page.locator('#baseline-steps button[data-remove="5395823"]').click()
        data = validate(SOURCE, TARGET, 10, ['5395823'])
        assert data['after']['hops'] == 9
        page.locator('#remove-node').select_option('12871993'); page.locator('#remove-button').click()
        assert validate(SOURCE, TARGET, 10, ['5395823', '12871993'])['after']['hops'] is None
        page.locator('[data-restore="5395823"]').click()
        assert validate(SOURCE, TARGET, 10, ['12871993'])['after']['hops'] is None
        # Selecting a removed node as endpoint restores it; endpoints never appear as removal options.
        page.locator('#source').select_option('12871993')
        validate('12871993', TARGET, 10, [])
        assert page.locator('#remove-node option[value="12871993"]').count() == 0
        assert page.locator(f'#remove-node option[value="{TARGET}"]').count() == 0
        page.locator('#source').select_option(SOURCE)
        page.locator('#swap').click(); validate(TARGET, SOURCE, 10, [])
        page.locator('#target').select_option(TARGET); validate(TARGET, TARGET, 10, [])
        # Invalid thresholds must clear stale results and prevent downloading a previous experiment.
        for value in ['0', '-1', '1.5', '', '9007199254740992']:
            page.locator('#threshold').fill(value)
            assert page.locator('#input-error').inner_text()
            assert page.locator('#download').is_disabled()
            assert page.locator('#comparison tr').count() == 0
            assert page.locator('#baseline-graph svg').count() == 0
        page.locator('#threshold').fill('1')
        rng = random.Random(20261019)
        ids = sorted(graph)
        for _ in range(24):
            s, t = rng.sample(ids, 2)
            cutoff = rng.choice([1, 3, 5, 10, 20, 100])
            if not page.locator('#reset').is_disabled(): page.locator('#reset').click()
            page.locator('#source').select_option(s); page.locator('#target').select_option(t)
            page.locator('#threshold').fill(str(cutoff))
            g = filtered(graph, cutoff)
            nodes = nx.shortest_path(g, s, t) if nx.has_path(g, s, t) else []
            removals = rng.sample(nodes[1:-1], min(2, len(nodes[1:-1])))
            if not removals: removals = [rng.choice([n for n in ids if n not in (s, t)])]
            for n in removals:
                page.locator('#remove-node').select_option(n); page.locator('#remove-button').click()
            validate(s, t, cutoff, removals)
        # Mobile controls and keyboard usage, with real exported results after the interaction.
        page.set_viewport_size({'width': 390, 'height': 844})
        page.locator('#reset').click()
        page.locator('#source').select_option(SOURCE); page.locator('#target').select_option(TARGET)
        page.locator('#threshold').fill('10')
        page.locator('#remove-node').select_option('12871993')
        page.locator('#remove-button').focus(); page.keyboard.press('Enter')
        validate(SOURCE, TARGET, 10, ['12871993'])
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors, errors
        assert not external, external
        counters.update({'browser': browser.version, 'page_errors': errors, 'external_requests': external,
                         'mobile_width': 390, 'invalid_threshold_cases': 5, 'seed': 20261019})
        browser.close()
    return counters, examples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    assert nx.__version__ == '3.4.2'
    run(['scripts/import_larva.py', '--check'])
    graph = raw_reference()
    with tempfile.TemporaryDirectory(prefix='larva-check-') as tmp:
        directory = Path(tmp)
        common = ['examples/larva/connections.csv', '--nodes', 'examples/larva/nodes.csv',
                  '--provenance', 'examples/larva/provenance.json', '--source', SOURCE, '--target', TARGET]
        for module, extra, shipped in [
            ('connectome_audit.explorer', [], 'larva-demo'),
            ('connectome_audit', ['--thresholds', '1,3,5,10,20', '--single-node-failure'], 'larva-audit'),
        ]:
            out = directory / shipped
            run(['-m', module, *common, *extra, '--output', str(out)])
            for name in ['report.json', 'report.html', 'COMPLETE.json']:
                assert (out / name).read_bytes() == (ROOT / 'results' / shipped / name).read_bytes(), f'Stale {shipped}/{name}'
        cli_checks = check_cli(graph)
        browser, examples = verify_browser(graph, directory, args.record)
    evidence = {'schema': 'connectome-real-data-verification/v1', 'status': 'passed',
                'reference': 'NetworkX 3.4.2 on independently parsed original eLife ZIP; shortest lengths and every witness edge checked',
                'source_nodes': len(graph), 'source_edges': graph.number_of_edges(),
                'source_synapses': sum(w['weight'] for _, _, w in graph.edges(data=True)),
                'cli_baseline_and_removal_checks': cli_checks, 'browser': browser, 'worked_example': examples,
                'deterministic_extraction_and_bundles': True,
                'limitations': ['Software and data-transformation checks, not biological validation.',
                                'Browser coverage: Linux Chromium only. Seeded queries are representative, not exhaustive.']}
    names = ['tests/test_explorer.py', 'scripts/import_larva.py', 'scripts/verify_larva.py', 'src/connectome_audit/explorer.py',
             'src/connectome_audit/explorer.js', 'src/connectome_audit/explorer.css', 'src/connectome_audit/explorer.html']
    names += [str(p.relative_to(ROOT)) for p in (ROOT / 'examples/larva').rglob('*') if p.is_file()]
    names += [str(p.relative_to(ROOT)) for p in (ROOT / 'results/larva-demo').glob('*') if p.is_file()]
    names += [str(p.relative_to(ROOT)) for p in (ROOT / 'results/larva-audit').glob('*') if p.is_file()]
    evidence['verified_files'] = {name: sha((ROOT / name).read_bytes()) for name in sorted(names)}
    if args.record:
        (ROOT / 'results/larva-verification.json').write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
    print(json.dumps(evidence, sort_keys=True))


if __name__ == '__main__':
    main()
