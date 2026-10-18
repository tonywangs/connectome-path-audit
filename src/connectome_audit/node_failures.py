"""Query-relative single intermediate-node failures, bounded by a baseline path."""
from collections import deque


class RemovalWorkExhausted(Exception):
    pass


def analyze_node_failures(graph, analysis, budget):
    """Augment baseline results. Never mutate graph or baseline witnesses.

    Every critical eligible node lies inside any fixed source-target path.
    Removing a node outside it leaves that witness intact. Endpoints are never
    eligible. Suppressing visits to the removed node suppresses all its incident
    edges, including outgoing edges because that node can never be expanded.
    When both extensions are requested, the CLI runs edge analysis first; its
    work consumes the shared removal ceilings before node trials begin.
    """
    prior = analysis.get('single_edge_failure', {})
    prior_tested = prior.get('tested_removals', 0)
    prior_work = prior.get('traversal_operations', 0)
    tested = work = 0

    def tick():
        nonlocal work
        if prior_work + work >= budget.limits.removal_operations:
            raise RemovalWorkExhausted
        budget.tick()
        work += 1

    for threshold in analysis['thresholds']:
        adjacency = {}
        for (a, b), count in sorted(graph.edges.items()):
            budget.tick()
            if count >= threshold:
                adjacency.setdefault(a, []).append(b)
        for r in analysis['results']:
            if r['threshold'] != threshold:
                continue
            budget.tick()
            failure = {'status': 'complete', 'candidates': [], 'critical_nodes': [],
                       'candidate_count': 0, 'untested_noncritical_nodes': 0}
            r['single_node_failure'] = failure
            if r['status'] != 'reachable':
                failure['status'] = ('initially_unreachable' if r['status'] == 'no_path_in_supplied_graph'
                                     else 'missing_node')
                continue
            candidates = r['path'][1:-1]
            failure['candidate_count'] = len(candidates)
            failure['untested_noncritical_nodes'] = len(graph.nodes) - len({r['source'], r['target']}) - len(candidates)
            for removed in candidates:
                budget.tick()
                item = {'node': removed,
                        'status': 'unresolved', 'reason': None, 'path': [], 'edge_counts': [],
                        'search_complete': False, 'visited_nodes': None}
                failure['candidates'].append(item)
                if prior_tested + tested >= budget.limits.candidate_removals:
                    item['reason'] = 'candidate_removal_limit'
                    failure['status'] = 'partial'
                    continue
                if prior_work + work >= budget.limits.removal_operations:
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
                            if neighbor != removed and neighbor not in parent:
                                parent[neighbor] = node
                                todo.append(neighbor)
                    item['visited_nodes'] = len(parent)
                    if r['target'] not in parent:
                        item.update(status='disconnected', search_complete=True)
                        failure['critical_nodes'].append(removed)
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
                            if removed in (a, b) or count < threshold:
                                raise AssertionError('invalid alternative witness')
                            counts.append(count)
                        item.update(status='alternative_path', path=path, edge_counts=counts)
                except RemovalWorkExhausted:
                    item['reason'] = 'removal_operation_limit'
                    failure['status'] = 'partial'
    analysis['single_node_failure'] = {
        'schema': 'connectome-single-node-failure/v1',
        'status': 'partial' if any(r['single_node_failure']['status'] == 'partial' for r in analysis['results']) else 'complete',
        'candidate_strategy': 'intermediate nodes of deterministic baseline witness; all other eligible nodes preserve that witness',
        'removal_unit': 'node and all incoming and outgoing edges, including self-loops',
        'endpoint_policy': 'exclude source and target',
        'source_equals_target': 'zero-hop identity preserved; no candidates',
        'prior_edge_removals': prior_tested, 'prior_edge_traversal_operations': prior_work,
        'tested_removals': tested, 'traversal_operations': work,
        'interpretation': 'Query-relative graph operation, not a validated neuronal intervention or biological importance. Missing connections can change every conclusion.'}
    return analysis
