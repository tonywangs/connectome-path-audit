"""Query-relative single aggregated edge failures, bounded by a baseline path."""
from collections import deque


class RemovalWorkExhausted(Exception):
    pass


def analyze_failures(graph, analysis, budget):
    """Augment baseline results. Never mutate graph or baseline witnesses.

    Every critical edge must lie on any fixed source-target path: removing an
    edge outside that path leaves it intact. Thus only baseline edges need BFS.
    """
    tested = work = 0

    def tick():
        nonlocal work
        if work >= budget.limits.removal_operations:
            raise RemovalWorkExhausted
        budget.tick()
        work += 1

    for threshold in analysis['thresholds']:
        adjacency = {}
        retained = 0
        for (a, b), count in sorted(graph.edges.items()):
            budget.tick()
            if count >= threshold:
                adjacency.setdefault(a, []).append(b)
                retained += 1
        for r in analysis['results']:
            if r['threshold'] != threshold:
                continue
            budget.tick()
            failure = {'status': 'complete', 'candidates': [], 'critical_edges': [],
                       'candidate_count': 0, 'untested_noncritical_edges': 0}
            r['single_edge_failure'] = failure
            if r['status'] != 'reachable':
                failure['status'] = ('initially_unreachable' if r['status'] == 'no_path_in_supplied_graph'
                                     else 'missing_node')
                continue
            candidates = list(zip(r['path'], r['path'][1:]))
            failure['candidate_count'] = len(candidates)
            failure['untested_noncritical_edges'] = retained - len(candidates)
            for removed in candidates:
                budget.tick()
                item = {'edge': list(removed), 'synapses': graph.edges[removed],
                        'status': 'unresolved', 'reason': None, 'path': [], 'edge_counts': [],
                        'search_complete': False, 'visited_nodes': None}
                failure['candidates'].append(item)
                if tested >= budget.limits.candidate_removals:
                    item['reason'] = 'candidate_removal_limit'
                    failure['status'] = 'partial'
                    continue
                if work >= budget.limits.removal_operations:
                    item['reason'] = 'removal_operation_limit'
                    failure['status'] = 'partial'
                    continue
                tested += 1
                parent = {r['source']: None}
                todo = deque(parent)
                try:
                    while todo and r['target'] not in parent:
                        tick()
                        node = todo.popleft()
                        for neighbor in adjacency.get(node, ()):
                            tick()
                            if (node, neighbor) != removed and neighbor not in parent:
                                parent[neighbor] = node
                                todo.append(neighbor)
                    item['visited_nodes'] = len(parent)
                    if r['target'] not in parent:
                        item.update(status='disconnected', search_complete=True)
                        failure['critical_edges'].append(list(removed))
                    else:
                        path = []
                        node = r['target']
                        while node is not None:
                            budget.witness()
                            path.append(node)
                            node = parent[node]
                        path.reverse()
                        counts = []
                        # Replay before reporting. Tests additionally use an independent oracle.
                        for a, b in zip(path, path[1:]):
                            budget.tick()
                            count = graph.edges.get((a, b), 0)
                            if (a, b) == removed or count < threshold:
                                raise AssertionError('invalid alternative witness')
                            counts.append(count)
                        item.update(status='alternative_path', path=path, edge_counts=counts)
                except RemovalWorkExhausted:
                    item['reason'] = 'removal_operation_limit'
                    failure['status'] = 'partial'
    analysis['single_edge_failure'] = {
        'schema': 'connectome-single-edge-failure/v1',
        'status': 'partial' if any(r['single_edge_failure']['status'] == 'partial' for r in analysis['results']) else 'complete',
        'candidate_strategy': 'edges of deterministic baseline witness; all other retained edges preserve that witness',
        'removal_unit': 'entire aggregated directed edge',
        'tested_removals': tested, 'traversal_operations': work,
        'interpretation': 'Query-relative graph operation, not a validated neuronal intervention or biological importance. Missing connections can change every conclusion.'}
    return analysis
