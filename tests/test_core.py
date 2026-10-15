import csv
from dataclasses import replace
import io
import json
from pathlib import Path
import random
import tempfile
import unittest

import networkx as nx
from connectome_audit.core import AuditError, Budget, LimitError, Limits, MAX_COUNT, analyze
from connectome_audit.ingest import load_graph

ROOT = Path(__file__).resolve().parents[1]


class Fixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.connections = self.root / 'connections.csv'
        self.nodes = self.root / 'nodes.csv'
        self.provenance = self.root / 'provenance.json'
        self.provenance.write_bytes((ROOT / 'examples/provenance.json').read_bytes())
        self.connections.write_text('source,target,synapses\na,b,5\nb,c,7\n')
        self.nodes.write_text('node_id,label\na,Alpha\nb,Beta\nc,Gamma\nisolated,Alone\n')

    def load(self, **limits):
        budget = Budget(replace(Limits(), **limits))
        return load_graph(self.connections, self.nodes, self.provenance, budget), budget


class Semantics(Fixtures):
    def test_boundaries_duplicates_cycles_identity_missing_and_direction(self):
        self.connections.write_text('source,target,synapses\na,b,2\na,b,3\nb,c,7\nc,a,1\na,a,8\n')
        graph, budget = self.load()
        result = analyze(graph, ['a', 'c', 'absent', 'isolated'], ['c', 'a', 'absent', 'isolated'], [1, 5, 6, 9], budget)
        index = {(r['source'], r['target'], r['threshold']): r for r in result['results']}
        self.assertEqual(index['a', 'c', 5]['path'], ['a', 'b', 'c'])
        self.assertEqual(index['a', 'c', 5]['edge_counts'], [5, 7])
        self.assertEqual(index['a', 'c', 6]['status'], 'no_path_in_supplied_graph')
        self.assertEqual(index['c', 'a', 5]['status'], 'no_path_in_supplied_graph')
        self.assertEqual(index['isolated', 'isolated', 9]['hops'], 0)
        self.assertEqual(index['a', 'a', 9]['path'], ['a'])
        self.assertEqual(index['absent', 'absent', 1]['status'], 'missing_node')
        self.assertEqual(index['absent', 'absent', 1]['missing_ids'], ['absent'])
        self.assertEqual(graph.duplicate_rows, 1)
        self.assertEqual(graph.self_loop_edges, 1)

    def test_numeric_ids_are_strings_and_lexicographic_tie_break(self):
        self.connections.write_text('source,target,synapses\n001,2,9\n001,10,9\n2,720575940628731140,9\n10,720575940628731140,9\n')
        graph, budget = self.load()
        r = analyze(graph, ['001'], ['720575940628731140'], [9], budget)['results'][0]
        self.assertEqual(r['path'], ['001', '10', '720575940628731140'])

    def test_empty_graph_and_declared_isolate(self):
        self.connections.write_text('source,target,synapses\n')
        graph, budget = self.load()
        self.assertEqual(analyze(graph, ['a'], ['b'], [1], budget)['results'][0]['status'], 'no_path_in_supplied_graph')
        graph = load_graph(self.connections, None, self.provenance, Budget(Limits()))
        self.assertFalse(graph.nodes)

    def test_exactly_twelve_thresholds_and_safe_maximum(self):
        graph, budget = self.load()
        result = analyze(graph, ['a'], ['c'], list(range(1, 13)), budget)
        self.assertEqual(len(result['results']), 12)
        self.connections.write_text(f'source,target,synapses\na,b,{MAX_COUNT}\n')
        graph, budget = self.load()
        r = analyze(graph, ['a'], ['b'], [MAX_COUNT], budget)['results'][0]
        self.assertEqual(r['edge_counts'], [MAX_COUNT])
        self.assertEqual(r['hops'], 1)

    def test_threshold_and_query_validation(self):
        graph, _ = self.load()
        for thresholds in ([], [1, 1], list(range(1, 14)), [0], [-1], [MAX_COUNT + 1], [True], [1.0]):
            with self.subTest(thresholds=thresholds), self.assertRaises(AuditError):
                analyze(graph, ['a'], ['b'], thresholds, Budget(Limits()))
        with self.assertRaises(LimitError):
            analyze(graph, ['a', 'b'], ['a', 'b'], [1], Budget(replace(Limits(), queries=3)))
        for sources, targets in (([], ['b']), (['a'], []), ([' a'], ['b'])):
            with self.assertRaises(AuditError):
                analyze(graph, sources, targets, [1], Budget(Limits()))


class IndependentReference(Fixtures):
    def test_300_seeded_graphs(self):
        self.assertEqual(nx.__version__, '3.4.2', 'Use the pinned independent reference')
        findings = witnesses = 0
        for seed in range(300):
            rng = random.Random(seed)
            n = rng.randint(3, 12)
            ids = ['001', '720575940628731140'] + [f'n{i:02}' for i in range(n - 2)]
            # Last declared node is always isolated. Other nodes can form cycles,
            # self-loops, ties, disjoint components and duplicate records.
            raw = []
            for a in ids[:-1]:
                for b in ids[:-1]:
                    if rng.random() < .24:
                        raw.append((a, b, rng.randint(1, 12)))
                        if rng.random() < .3:
                            raw.append((a, b, rng.randint(1, 8)))
            rng.shuffle(raw)
            with self.connections.open('w', newline='') as f:
                writer = csv.writer(f); writer.writerow(['source', 'target', 'synapses']); writer.writerows(raw)
            with self.nodes.open('w', newline='') as f:
                writer = csv.writer(f); writer.writerow(['node_id', 'label']); writer.writerows((i, '') for i in ids)
            graph, budget = self.load()
            thresholds = [1, 2, 5, 8, 12, 20]
            result = analyze(graph, ids + ['absent'], ids + ['absent'], thresholds, budget)
            # Independent aggregation from original records, not production graph.
            totals = {}
            for a, b, count in raw:
                totals[a, b] = totals.get((a, b), 0) + count
            oracles = {}
            for t in thresholds:
                ref = nx.DiGraph(); ref.add_nodes_from(ids)
                ref.add_edges_from((a, b) for (a, b), count in totals.items() if count >= t)
                distances = dict(nx.all_pairs_shortest_path_length(ref))
                # Independent Floyd-Warshall matrix in addition to pinned BFS.
                matrix = [[0 if i == j else (1 if ref.has_edge(a, b) else float('inf'))
                           for j, b in enumerate(ids)] for i, a in enumerate(ids)]
                for k in range(n):
                    for i in range(n):
                        for j in range(n):
                            matrix[i][j] = min(matrix[i][j], matrix[i][k] + matrix[k][j])
                for i, a in enumerate(ids):
                    for j, b in enumerate(ids):
                        self.assertEqual(distances[a].get(b, float('inf')), matrix[i][j], (seed, t, a, b))
                oracles[t] = ref, distances
            previous = {}
            for r in result['results']:
                findings += 1
                a, b, t = r['source'], r['target'], r['threshold']
                ref, distances = oracles[t]
                if a == 'absent' or b == 'absent':
                    self.assertEqual(r['status'], 'missing_node')
                    self.assertIsNone(r['hops']); self.assertEqual(r['path'], [])
                    continue
                hops = distances[a].get(b)
                self.assertEqual(r['hops'], hops, (seed, a, b, t))
                self.assertEqual(r['status'], 'reachable' if hops is not None else 'no_path_in_supplied_graph')
                distance = hops if hops is not None else float('inf')
                self.assertGreaterEqual(distance, previous.get((a, b), 0), 'threshold monotonicity')
                previous[a, b] = distance
                if hops is None:
                    self.assertEqual(r['path'], []); self.assertEqual(r['edge_counts'], [])
                    continue
                witnesses += 1
                path = r['path']
                self.assertEqual((path[0], path[-1], len(path) - 1), (a, b, hops))
                self.assertEqual(len(set(path)), len(path))
                counts = [totals[x, y] for x, y in zip(path, path[1:])]
                self.assertEqual(r['edge_counts'], counts)
                self.assertTrue(all(c >= t for c in counts))
                self.assertEqual(r['bottleneck'], min(counts) if counts else None)
                # Greedy choice constrained by independently computed distance-to-target
                # checks the canonical tie-break without enumerating shortest paths.
                canonical, current = [a], a
                for remaining in range(hops - 1, -1, -1):
                    current = min(v for v in ref.successors(current) if distances[v].get(b) == remaining)
                    canonical.append(current)
                self.assertEqual(path, canonical, (seed, a, b, t))
            # CSV row order must not affect algorithm output.
            if seed % 25 == 0:
                with self.connections.open('w', newline='') as f:
                    writer = csv.writer(f); writer.writerow(['source', 'target', 'synapses']); writer.writerows(reversed(raw))
                graph2, budget2 = self.load()
                self.assertEqual(result, analyze(graph2, ids[::-1] + ['absent'], ids[::-1] + ['absent'], thresholds[::-1], budget2))
        print(f'Independent reference: 300 seeds, {findings} findings, {witnesses} verified witnesses; NetworkX 3.4.2 + Floyd-Warshall')
