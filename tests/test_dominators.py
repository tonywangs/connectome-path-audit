"""Independent exhaustive deletion and pinned NetworkX dominator comparison."""
import csv
from copy import deepcopy
from dataclasses import replace
import random
from unittest.mock import patch

import networkx as nx
from connectome_audit.core import Budget, Limits, LimitError, analyze
from connectome_audit.dominators import analyze_dominators
from test_core import Fixtures
import test_failures


class DominatorOutputRegressions(test_failures.OutputFailures):
    def args(self, output=None):
        return super().args(output) + ['--dominator-node-failure', '--dominator-witnesses']


class Dominators(Fixtures):
    def test_300_seeded_graphs(self):
        findings = witnesses = removals = 0
        for seed in range(300):
            rng = random.Random(20261018 + seed)
            ids = ['001', '720575940628731140'] + [f'n{i}' for i in range(rng.randint(3, 8))]
            raw = []
            for a in ids[:-1]:
                for b in ids[:-1]:
                    if rng.random() < .32:
                        raw.append((a, b, rng.randint(1, 8)))
                        if rng.random() < .4: raw.append((a, b, rng.randint(1, 4)))
            with self.connections.open('w', newline='') as f:
                w = csv.writer(f); w.writerow(['source', 'target', 'synapses']); w.writerows(raw)
            with self.nodes.open('w', newline='') as f:
                w = csv.writer(f); w.writerow(['node_id', 'label']); w.writerows((n, '') for n in ids)
            graph, budget = self.load()
            original = deepcopy(graph)
            result = analyze(graph, ids + ['absent'], ids + ['absent'], [1, 5, 9], budget)
            baseline = deepcopy(result)
            analyze_dominators(graph, result, budget, witnesses=True)
            self.assertEqual(graph, original)
            self.assertEqual(result['dominator_node_failure']['status'], 'complete')
            self.assertEqual(result['dominator_node_failure']['witness_status'], 'complete')
            for old, new in zip(baseline['results'], result['results']):
                self.assertEqual(old, {k: v for k, v in new.items() if k != 'dominator_node_failure'})
            for threshold in result['thresholds']:
                g = nx.DiGraph(); g.add_nodes_from(ids)
                g.add_edges_from(e for e, count in graph.edges.items() if count >= threshold)
                deleted = {}
                for node in ids:
                    h = g.copy(); h.remove_node(node)
                    deleted[node] = dict(nx.all_pairs_shortest_path_length(h)); removals += 1
                trees = {s: nx.immediate_dominators(g, s) for s in ids}
                for r in result['results']:
                    if r['threshold'] != threshold: continue
                    findings += 1
                    f = r['dominator_node_failure']; s, t = r['source'], r['target']
                    if 'absent' in (s, t):
                        self.assertEqual(f['status'], 'missing_node'); continue
                    if not nx.has_path(g, s, t):
                        self.assertEqual(f['status'], 'initially_unreachable'); continue
                    expected = {n for n in ids if n not in (s, t) and t not in deleted[n][s]}
                    ancestors, node = set(), t
                    while node != s:
                        node = trees[s][node]
                        if node != s: ancestors.add(node)
                    self.assertEqual(expected, ancestors)
                    self.assertEqual(set(f['critical_nodes']), expected, (seed, s, t, threshold))
                    self.assertTrue(f['classification_complete'])
                    self.assertEqual([c['node'] for c in f['candidates']], r['path'][1:-1])
                    for c in f['candidates']:
                        n = c['node']
                        self.assertEqual(c['status'], 'critical' if n in expected else 'noncritical')
                        if n in expected:
                            self.assertEqual(c['witness_status'], 'not_applicable'); continue
                        path = c['path']; witnesses += 1
                        self.assertEqual(c['witness_status'], 'available')
                        self.assertEqual((path[0], path[-1]), (s, t)); self.assertNotIn(n, path)
                        self.assertEqual(len(path) - 1, deleted[n][s][t])
                        self.assertTrue(all(g.has_edge(a, b) for a, b in zip(path, path[1:])))
                        self.assertEqual(c['edge_counts'], [graph.edges[a, b] for a, b in zip(path, path[1:])])
            if seed % 50 == 0:
                b = Budget(Limits())
                repeated = analyze(graph, list(reversed(ids)) + ['absent'], ids + ['absent'], [9, 5, 1], b)
                analyze_dominators(graph, repeated, b, witnesses=True)
                self.assertEqual(result, repeated)
        print(f'Dominator reference: 300 seeds, {findings} findings, {removals} full-node removals, {witnesses} independent witnesses')

    def fixture_result(self, witnesses=False, **limits):
        self.connections.write_text('source,target,synapses\na,b,5\nb,c,5\na,d,5\nd,c,5\nc,e,5\ne,z,5\nc,c,5\nz,a,1\n')
        graph, budget = self.load(**limits)
        result = analyze(graph, ['a'], ['z', 'a', 'isolated', 'absent'], [5], budget)
        analyze_dominators(graph, result, budget, witnesses=witnesses)
        f = next(r['dominator_node_failure'] for r in result['results'] if r['target'] == 'z')
        return graph, budget, result, f

    def test_classification_and_witness_budgets_separate(self):
        _, _, result, f = self.fixture_result()
        self.assertEqual(f['critical_nodes'], ['c', 'e'])
        self.assertEqual(f['candidates'][0]['witness_status'], 'not_requested')
        self.assertEqual(result['dominator_node_failure']['witness_searches'], 0)
        for limits in [dict(dominator_operations=1), dict(dominator_source_operations=1)]:
            _, _, result, f = self.fixture_result(**limits)
            self.assertEqual(f['status'], 'partial'); self.assertEqual(f['critical_nodes'], [])
            self.assertTrue(all(c['status'] == 'unresolved' for c in f['candidates']))
            self.assertEqual(result['dominator_node_failure']['traversal_operations'], 1)
        _, _, result, f = self.fixture_result(witnesses=True, dominator_witness_operations=1)
        self.assertTrue(f['classification_complete']); self.assertEqual(f['critical_nodes'], ['c', 'e'])
        self.assertEqual(f['candidates'][0]['witness_status'], 'unresolved')
        self.assertEqual(f['candidates'][0]['path'], [])
        self.assertEqual(result['dominator_node_failure']['status'], 'complete')
        self.assertEqual(result['dominator_node_failure']['witness_status'], 'partial')

    def test_hard_limits(self):
        graph, _, _, _ = self.fixture_result()
        for field in ['operations', 'witness_nodes']:
            b = Budget(Limits()); result = analyze(graph, ['a'], ['z'], [5], b)
            b.limits = replace(b.limits, **{field: getattr(b, field) + 1})
            with self.assertRaises(LimitError): analyze_dominators(graph, result, b, witnesses=True)
        b = Budget(Limits()); result = analyze(graph, ['a'], ['z'], [5], b)
        with patch.object(b, 'clock', return_value=b.deadline):
            with self.assertRaises(LimitError): analyze_dominators(graph, result, b)

    def test_iterative_deep_chain_and_shared_tree(self):
        self.connections.write_text('source,target,synapses\n' + ''.join(f'n{i},n{i+1},5\n' for i in range(1500)))
        graph, b = self.load(); result = analyze(graph, ['n0'], ['n1499', 'n1500'], [5], b)
        analyze_dominators(graph, result, b)
        self.assertEqual(len(result['dominator_node_failure']['sources']), 1)
        self.assertEqual([len(r['dominator_node_failure']['critical_nodes']) for r in result['results']], [1498, 1499])

    def test_source_reset_and_atomic_ancestor_exhaustion(self):
        from connectome_audit.dominators import immediate_dominators
        self.connections.write_text('source,target,synapses\na,b,5\nb,c,5\nc,d,5\nx,y,5\ny,z,5\n')
        graph, b = self.load()
        result = analyze(graph, ['a','x'], ['d','z'], [1], b)
        # The longer source exceeds its own allowance; later source gets a fresh
        # allowance and can still complete under the extension-wide ceiling.
        analyze_dominators(graph, result, Budget(replace(Limits(), dominator_source_operations=20)))
        f = {(r['source'],r['target']):r['dominator_node_failure'] for r in result['results']}
        self.assertEqual(f['a','d']['status'], 'partial')
        self.assertEqual(f['x','z']['critical_nodes'], ['y'])
        ticks = []
        immediate_dominators({'a':['b'],'b':['c'],'c':['d']},'a',lambda:ticks.append(1))
        b = Budget(replace(Limits(),dominator_source_operations=len(ticks)+1))
        result = analyze(graph,['a'],['d'],[1],b)
        analyze_dominators(graph,result,b)
        f = result['results'][0]['dominator_node_failure']
        self.assertEqual(f['status'],'partial'); self.assertEqual(f['critical_nodes'],[])
        self.assertTrue(all(c['status']=='unresolved' for c in f['candidates']))
        self.assertEqual(result['dominator_node_failure']['sources'][0]['tree_status'],'complete')

    def test_witness_search_limit_and_combined_extensions(self):
        from connectome_audit.node_failures import analyze_node_failures
        from connectome_audit.failures import analyze_failures
        from connectome_audit import cli
        self.connections.write_text('source,target,synapses\na,b,5\nb,c,5\nc,z,5\na,x,5\nx,z,5\na,y,5\ny,z,5\n')
        graph,b=self.load(dominator_witness_searches=1)
        result=analyze(graph,['a'],['c','z'],[1],b)
        analyze_failures(graph,result,b); analyze_node_failures(graph,result,b)
        before=deepcopy(result)
        analyze_dominators(graph,result,b,witnesses=True)
        self.assertEqual(result['single_node_failure'],before['single_node_failure'])
        self.assertEqual(result['single_edge_failure'],before['single_edge_failure'])
        self.assertEqual(result['dominator_node_failure']['witness_searches'],1)
        # Another diamond creates two independent noncritical candidates.
        self.connections.write_text('source,target,synapses\na,b,5\na,x,5\nb,c,5\nx,c,5\nc,d,5\nc,y,5\nd,z,5\ny,z,5\n')
        graph,b=self.load(dominator_witness_searches=1)
        result=analyze(graph,['a'],['z'],[1],b)
        analyze_dominators(graph,result,b,witnesses=True)
        candidates=result['results'][0]['dominator_node_failure']['candidates']
        self.assertEqual([c['witness_status'] for c in candidates],['available','not_applicable','unresolved'])
        self.assertEqual(candidates[-1]['witness_reason'],'dominator_witness_search_limit')
        args=[str(self.connections),'--provenance',str(self.provenance),'--source','a','--target','z',
              '--thresholds','1','--output',str(self.root/'invalid'),'--dominator-witnesses']
        self.assertEqual(cli.main(args),2)
        self.assertFalse((self.root/'invalid').exists())
