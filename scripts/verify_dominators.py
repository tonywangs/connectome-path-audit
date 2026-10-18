"""Installed-artifact, offline-browser and paired benchmark verification."""
import csv
import hashlib
import json
import os
from pathlib import Path
import sys


def reference(report, inputs):
    import networkx as nx
    doc = json.loads(report.read_text())
    totals = {}
    with (inputs / 'connections.csv').open() as f:
        for row in csv.DictReader(f):
            key = row['source'], row['target']
            totals[key] = totals.get(key, 0) + int(row['synapses'])
    findings = witnesses = 0
    for threshold in doc['thresholds']:
        g = nx.DiGraph(); g.add_nodes_from(n['id'] for n in doc['nodes'])
        g.add_edges_from(e for e, c in totals.items() if c >= threshold)
        trees = {}
        for r in doc['results']:
            if r['threshold'] != threshold: continue
            f = r['dominator_node_failure']; s,t = r['source'],r['target']; findings += 1
            if s not in g or t not in g:
                assert f['status'] == 'missing_node'; continue
            if not nx.has_path(g,s,t):
                assert f['status'] == 'initially_unreachable'; continue
            if s not in trees: trees[s] = nx.immediate_dominators(g,s)
            ancestors, node = set(), t
            while node != s:
                node = trees[s][node]
                if node != s: ancestors.add(node)
            if f['classification_complete']: assert set(f['critical_nodes']) == ancestors
            for c in f['candidates']:
                if c['status'] == 'unresolved':
                    assert c['path'] == [] and not f['classification_complete']; continue
                assert (c['status'] == 'critical') == (c['node'] in ancestors)
                h = g.copy(); h.remove_node(c['node'])
                assert (c['status'] == 'critical') == (not nx.has_path(h,s,t))
                if c['witness_status'] == 'available':
                    path = c['path']; witnesses += 1
                    assert path[0] == s and path[-1] == t and c['node'] not in path
                    assert len(path)-1 == nx.shortest_path_length(h,s,t)
                    assert all(h.has_edge(a,b) for a,b in zip(path,path[1:]))
                    assert c['edge_counts'] == [totals[a,b] for a,b in zip(path,path[1:])]
                else: assert c['path'] == c['edge_counts'] == []
    return {'findings': findings, 'independently_checked_witnesses': witnesses}


def verify(executable, temp, env, logs, browser_args, browser_inputs, node_args):
    from verify import ROOT, run, sha, verify_bundle
    from browser_check import check, check_partial, check_dominator_witness_state
    import networkx.algorithms.dominance as nxdom
    evidence = {'reference_version': 'NetworkX 3.4.2', 'reference_source_sha256': sha(nxdom.__file__)}
    node_args = [a for a in node_args if a != '--single-node-failure']
    example = temp/'dominator-example'
    before = {p.name:sha(p) for p in (ROOT/'examples/node-failure').iterdir()}
    evidence['example'] = run([executable,*node_args,'--dominator-node-failure','--dominator-witnesses','--output',example],temp,env,logs)
    evidence['example'].update(artifacts=verify_bundle(example), reference=reference(example/'report.json',ROOT/'examples/node-failure'))
    again = temp/'dominator-example-again'
    run([executable,*node_args,'--dominator-node-failure','--dominator-witnesses','--output',again],temp,{**env,'PYTHONHASHSEED':'73'},logs)
    assert verify_bundle(example) == verify_bundle(again)
    assert before == {p.name:sha(p) for p in (ROOT/'examples/node-failure').iterdir()}
    evidence['example'].update(byte_identical_repeated_outputs=True, unchanged_input_hashes=before)
    browser = temp/'dominator-browser'
    before = {p.name:sha(p) for p in browser_inputs.iterdir()}
    run([executable,*browser_args,'--dominator-node-failure','--dominator-witnesses','--output',browser],temp,env,logs)
    evidence['browser_reference'] = reference(browser/'report.json',browser_inputs)
    evidence['browser'] = check(browser/'report.html')
    assert before == {p.name:sha(p) for p in browser_inputs.iterdir()}
    partial = temp/'dominator-partial'
    run([executable,*node_args,'--dominator-node-failure','--max-dominator-operations','1','--output',partial],temp,env,logs)
    evidence['partial_browser'] = check_partial(partial/'report.html',kind='dom')
    evidence['partial_reference'] = reference(partial/'report.json',ROOT/'examples/node-failure')
    no_witness = temp/'dominator-no-witness'
    run([executable,*node_args,'--dominator-node-failure','--output',no_witness],temp,env,logs)
    d = json.loads((no_witness/'report.json').read_text())
    assert d['dominator_node_failure']['witness_searches'] == 0
    assert d['dominator_node_failure']['witness_status'] == 'not_requested'
    evidence['classification_only_browser'] = check_dominator_witness_state(no_witness/'report.html','not_requested')
    evidence['classification_only_reference'] = reference(no_witness/'report.json',ROOT/'examples/node-failure')
    exhausted = temp/'dominator-witness-exhausted'
    run([executable,*node_args,'--dominator-node-failure','--dominator-witnesses',
         '--max-dominator-witness-operations','1','--output',exhausted],temp,env,logs)
    d = json.loads((exhausted/'report.json').read_text())
    assert d['dominator_node_failure']['status'] == 'complete'
    assert d['dominator_node_failure']['witness_status'] == 'partial'
    evidence['exhausted_witness_browser'] = check_dominator_witness_state(exhausted/'report.html','unresolved')
    evidence['exhausted_witness_reference'] = reference(exhausted/'report.json',ROOT/'examples/node-failure')
    benchmark = temp/'dominator-benchmark.json'
    run([sys.executable,ROOT/'scripts/dominator_benchmark.py','--output',benchmark],temp,env,logs,timeout=180)
    evidence['benchmark'] = json.loads(benchmark.read_text())
    return evidence, example
