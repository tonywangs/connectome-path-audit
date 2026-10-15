import csv
from dataclasses import replace
import random
from unittest.mock import patch

import networkx as nx
from connectome_audit.core import Budget, Limits, LimitError, analyze
from connectome_audit.failures import analyze_failures
from test_core import Fixtures
import test_failures


class FailureOutputRegressions(test_failures.OutputFailures):
    """Run every transactional/cancellation regression through the new CLI option."""
    def args(self, output=None):
        return super().args(output) + ['--single-edge-failure']


class EdgeFailures(Fixtures):
    def run_analysis(self, sources, targets, thresholds, **limits):
        graph, budget = self.load(**limits)
        baseline = analyze(graph, sources, targets, thresholds, budget)
        before = dict(graph.edges)
        result = analyze_failures(graph, baseline, budget)
        self.assertEqual(before, graph.edges)
        return result

    def test_300_seeded_all_edge_removals(self):
        findings = removals = witnesses = critical = 0
        for seed in range(300):
            rng = random.Random(seed + 81000)
            ids = ['001', '720575940628731140'] + [f'n{i}' for i in range(rng.randint(2, 7))]
            raw = []
            for a in ids[:-1]:
                for b in ids[:-1]:
                    if rng.random() < .3:
                        raw.append((a, b, rng.randint(1, 8)))
                        if rng.random() < .35: raw.append((a, b, rng.randint(1, 4)))
            with self.connections.open('w', newline='') as f:
                w = csv.writer(f); w.writerow(['source', 'target', 'synapses']); w.writerows(raw)
            with self.nodes.open('w', newline='') as f:
                w = csv.writer(f); w.writerow(['node_id', 'label']); w.writerows((n, '') for n in ids)
            totals = {}
            for a, b, count in raw: totals[a, b] = totals.get((a, b), 0) + count
            result = self.run_analysis(ids + ['absent'], ids + ['absent'], [1, 4, 8, 12])
            self.assertEqual(result['single_edge_failure']['status'], 'complete')
            oracles = {}
            for t in result['thresholds']:
                g = nx.DiGraph(); g.add_nodes_from(ids)
                g.add_edges_from(e for e, count in totals.items() if count >= t)
                # Remove EVERY retained edge, including loops and edges outside the
                # baseline. Compute all-pairs reachability independently of candidates.
                deleted = {}
                for edge in list(g.edges):
                    h = g.copy(); h.remove_edge(*edge)
                    deleted[edge] = h, dict(nx.all_pairs_shortest_path_length(h))
                    removals += 1
                oracles[t] = g, deleted
            for r in result['results']:
                findings += 1
                f = r['single_edge_failure']; a, b, t = r['source'], r['target'], r['threshold']
                if a == 'absent' or b == 'absent':
                    self.assertEqual(f['status'], 'missing_node'); continue
                g, deleted = oracles[t]
                if not nx.has_path(g, a, b):
                    self.assertEqual(f['status'], 'initially_unreachable')
                    self.assertEqual(f['critical_edges'], []); continue
                expected = {e for e, (_, distances) in deleted.items() if b not in distances[a]}
                self.assertEqual(set(map(tuple, f['critical_edges'])), expected, (seed, a, b, t))
                critical += len(expected)
                self.assertEqual([tuple(c['edge']) for c in f['candidates']], list(zip(r['path'], r['path'][1:])))
                self.assertEqual(f['untested_noncritical_edges'], len(g.edges) - len(f['candidates']))
                for c in f['candidates']:
                    edge = tuple(c['edge']); h, distances = deleted[edge]
                    self.assertEqual(c['synapses'], totals[edge])
                    if edge in expected:
                        self.assertEqual(c['status'], 'disconnected'); self.assertTrue(c['search_complete'])
                        self.assertEqual(c['visited_nodes'], len(distances[a])); continue
                    self.assertEqual(c['status'], 'alternative_path')
                    path = c['path']; witnesses += 1
                    self.assertEqual((path[0], path[-1]), (a, b))
                    self.assertEqual(len(path) - 1, distances[a][b])
                    self.assertEqual(len(set(path)), len(path))
                    self.assertTrue(all(h.has_edge(x, y) and (x, y) != edge for x, y in zip(path, path[1:])))
                    self.assertEqual(c['edge_counts'], [totals[x, y] for x, y in zip(path, path[1:])])
                    # Independently select canonical shortest path from distances.
                    canonical, current = [a], a
                    for remaining in range(distances[a][b] - 1, -1, -1):
                        current = min(v for v in h.successors(current) if distances[v].get(b) == remaining)
                        canonical.append(current)
                    self.assertEqual(path, canonical)
            if seed % 50 == 0:
                self.assertEqual(result, self.run_analysis(ids[::-1] + ['absent'], ids[::-1] + ['absent'], [12, 8, 4, 1]))
        print(f'Edge failure reference: 300 seeds, {findings} findings, {removals} full-edge reference removals, {witnesses} alternative witnesses, {critical} critical findings')

    def test_duplicates_ties_loops_boundaries_and_identity(self):
        self.connections.write_text('source,target,synapses\na,b,2\na,b,3\nb,c,5\na,d,5\nd,c,5\nc,z,9\nz,a,1\na,a,9\n')
        result = self.run_analysis(['a', 'absent'], ['a', 'z', 'isolated', 'absent'], list(range(1, 13)))
        index = {(r['source'], r['target'], r['threshold']): r['single_edge_failure'] for r in result['results']}
        self.assertEqual(index['a', 'z', 5]['critical_edges'], [['c', 'z']])
        self.assertEqual(index['a', 'z', 5]['candidates'][0]['path'], ['a', 'd', 'c', 'z'])
        self.assertEqual(index['a', 'z', 6]['status'], 'initially_unreachable')
        self.assertEqual(index['a', 'a', 1]['candidate_count'], 0)
        self.assertEqual(index['absent', 'absent', 1]['status'], 'missing_node')

    def test_partial_and_hard_limits(self):
        r = self.run_analysis(['a'], ['c'], [1], candidate_removals=1)
        self.assertEqual(r['single_edge_failure']['status'], 'partial')
        c = r['results'][0]['single_edge_failure']['candidates']
        self.assertEqual([x['status'] for x in c], ['disconnected', 'unresolved'])
        self.assertEqual(c[1]['reason'], 'candidate_removal_limit')
        r = self.run_analysis(['a'], ['c'], [1], removal_operations=1)
        self.assertEqual(r['single_edge_failure']['traversal_operations'], 1)
        self.assertTrue(all(c['status'] == 'unresolved' for c in r['results'][0]['single_edge_failure']['candidates']))
        graph, budget = self.load()
        baseline = analyze(graph, ['a'], ['c'], [1], budget)
        budget.limits = replace(Limits(), operations=budget.operations + 1)
        with self.assertRaises(LimitError): analyze_failures(graph, baseline, budget)
        graph, budget = self.load()
        baseline = analyze(graph, ['a'], ['c'], [1], budget)
        with patch.object(budget, 'clock', return_value=budget.deadline):
            with self.assertRaises(LimitError): analyze_failures(graph, baseline, budget)
