"""Bounded iterative immediate dominators; optional, separately budgeted witnesses."""
from collections import deque


class DominatorExhausted(Exception):
    pass


class Work:
    def __init__(self, budget):
        self.budget = budget
        self.total = self.source = 0

    def tick(self):
        if self.total >= self.budget.limits.dominator_operations:
            raise DominatorExhausted('dominator_operation_limit')
        if self.source >= self.budget.limits.dominator_source_operations:
            raise DominatorExhausted('dominator_source_operation_limit')
        self.budget.tick()
        self.total += 1
        self.source += 1


def immediate_dominators(adjacency, source, tick):
    """CHK Figure 3, explicit DFS stack and postorder numbers; O(V+E) storage.

    Only return after convergence. Each DFS step, predecessor visit, sweep node
    and dominator-chain step is charged; unreachable predecessors are excluded.
    """
    seen = {source}
    stack = [(source, iter(adjacency.get(source, ())))]
    order, predecessors = [], {}
    while stack:
        tick()
        node, neighbors = stack[-1]
        neighbor = next(neighbors, None)
        if neighbor is None:
            order.append(node)
            stack.pop()
        else:
            predecessors.setdefault(neighbor, []).append(node)
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append((neighbor, iter(adjacency.get(neighbor, ()))))
    rank = {}
    for i, node in enumerate(order):
        tick()
        rank[node] = i
    parents = {source: source}
    changed = True
    while changed:
        changed = False
        for node in reversed(order[:-1]):
            tick()
            candidate = None
            for pred in predecessors[node]:
                tick()
                if pred not in parents:
                    continue
                if candidate is None:
                    candidate = pred
                    continue
                a, b = candidate, pred
                while a != b:
                    tick()
                    if rank[a] < rank[b]:
                        a = parents[a]
                    else:
                        b = parents[b]
                candidate = a
            assert candidate is not None
            if parents.get(node) != candidate:
                parents[node] = candidate
                changed = True
    return parents


def analyze_dominators(graph, analysis, budget, witnesses=False):
    """One tree per source/threshold, never publish an unconverged tree.

    Limits are shared over this extension, with an additional per-source ceiling.
    Witness BFS uses distinct ceilings; exhaustion cannot change classification.
    Global Budget errors still abort the report transaction, as for baseline work.
    """
    work = Work(budget)
    searches = witness_work = 0
    runs = []

    def witness_tick():
        nonlocal witness_work
        if witness_work >= budget.limits.dominator_witness_operations:
            raise DominatorExhausted('dominator_witness_operation_limit')
        budget.tick()
        witness_work += 1

    def alternative(r, removed, adjacency):
        nonlocal searches
        if searches >= budget.limits.dominator_witness_searches:
            return 'unresolved', 'dominator_witness_search_limit', [], []
        searches += 1
        parent = {r['source']: None}
        todo = deque(parent)
        try:
            while todo and r['target'] not in parent:
                witness_tick()
                node = todo.popleft()
                for neighbor in adjacency.get(node, ()):
                    witness_tick()
                    if neighbor != removed and neighbor not in parent:
                        parent[neighbor] = node
                        todo.append(neighbor)
            assert r['target'] in parent, 'noncritical node must have an alternative'
            path, node = [], r['target']
            while node is not None:
                witness_tick()
                budget.witness()
                path.append(node)
                node = parent[node]
            path.reverse()
            counts = []
            for a, b in zip(path, path[1:]):
                witness_tick()
                count = graph.edges.get((a, b), 0)
                assert removed not in (a, b) and count >= r['threshold']
                counts.append(count)
            return 'available', None, path, counts
        except DominatorExhausted as exc:
            return 'unresolved', str(exc), [], []

    for threshold in analysis['thresholds']:
        adjacency = {}
        # Construction is charged to the hard global budget; source searches to
        # both the hard budget and extension-specific ceilings.
        for (a, b), count in sorted(graph.edges.items()):
            budget.tick()
            if count >= threshold:
                adjacency.setdefault(a, []).append(b)
        groups = {}
        for r in analysis['results']:
            budget.tick()
            if r['threshold'] == threshold:
                groups.setdefault(r['source'], []).append(r)
        for source, results in groups.items():
            work.source = 0
            parents, reason = None, None
            needs_tree = any(r['status'] == 'reachable' and len(r['path']) > 2 for r in results)
            if needs_tree:
                try:
                    parents = immediate_dominators(adjacency, source, work.tick)
                except DominatorExhausted as exc:
                    reason = str(exc)
            for r in results:
                budget.tick()
                f = {'status': 'complete', 'classification_complete': True,
                     'critical_nodes': [], 'candidate_count': 0, 'candidates': [],
                     'untested_noncritical_nodes': 0}
                r['dominator_node_failure'] = f
                if r['status'] != 'reachable':
                    f.update(status='missing_node' if r['status'] == 'missing_node' else 'initially_unreachable',
                             classification_complete=False)
                    continue
                candidates = r['path'][1:-1]
                f['candidate_count'] = len(candidates)
                f['untested_noncritical_nodes'] = len(graph.nodes) - len({source, r['target']}) - len(candidates)
                critical, query_reason = set(), reason
                if candidates and parents is not None:
                    try:
                        node = parents[r['target']]
                        while node != source:
                            work.tick()
                            critical.add(node)
                            node = parents[node]
                    except DominatorExhausted as exc:
                        critical, query_reason = set(), str(exc)
                if candidates and query_reason:
                    f.update(status='partial', classification_complete=False)
                for node in candidates:
                    budget.tick()
                    classification = 'unresolved' if query_reason else ('critical' if node in critical else 'noncritical')
                    item = {'node': node, 'status': classification, 'reason': query_reason,
                            'witness_status': ('not_applicable' if classification == 'critical' else
                                               ('unresolved' if classification == 'unresolved' and witnesses else 'not_requested')),
                            'witness_reason': 'classification_unresolved' if classification == 'unresolved' and witnesses else None, 'path': [], 'edge_counts': []}
                    if classification == 'critical':
                        f['critical_nodes'].append(node)
                    elif classification == 'noncritical' and witnesses:
                        item['witness_status'], item['witness_reason'], item['path'], item['edge_counts'] = alternative(r, node, adjacency)
                    f['candidates'].append(item)
            runs.append({'source': source, 'threshold': threshold,
                         'tree_status': 'complete' if parents is not None else ('unresolved' if needs_tree else 'not_needed'),
                         'reason': reason, 'operations': work.source})
    findings = [r['dominator_node_failure'] for r in analysis['results']]
    analysis['dominator_node_failure'] = {
        'schema': 'connectome-dominator-node-failure/v1',
        'status': 'partial' if any(f['status'] == 'partial' for f in findings) else 'complete',
        'algorithm': 'Cooper-Harvey-Kennedy iterative immediate dominators (Figure 3)',
        'reference': 'https://www.cs.tufts.edu/~nr/cs257/archive/keith-cooper/dom14.pdf',
        'endpoint_policy': 'exclude source and target',
        'initially_unreachable': 'no removal-induced disconnection claim',
        'source_equals_target': 'zero-hop identity; no critical intermediates',
        'candidate_strategy': 'baseline intermediate nodes; all other eligible nodes preserve baseline witness',
        'traversal_operations': work.total, 'sources': runs,
        'witnesses_requested': witnesses, 'witness_searches': searches,
        'witness_operations': witness_work,
        'witness_status': ('partial' if any(c['witness_status'] == 'unresolved' for f in findings for c in f['candidates'])
                           else ('complete' if witnesses else 'not_requested')),
        'interpretation': 'Graph-node removal is not a validated neuronal intervention. Missing connections can change every conclusion.'}
    return analysis
