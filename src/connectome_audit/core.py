"""Bounded, deterministic unweighted directed graph analysis."""
from collections import deque
from dataclasses import asdict, dataclass
import time

MAX_COUNT = 9_007_199_254_740_991  # Exact in JSON consumers using IEEE-754.


class AuditError(Exception):
    """Invalid input or incomplete computation; never evidence of no path."""


class LimitError(AuditError):
    pass


@dataclass(frozen=True)
class Limits:
    input_bytes: int = 8 * 1024 * 1024  # combined connections, nodes, provenance
    nodes: int = 10_000
    edges: int = 100_000  # distinct directed pairs, including self-loops
    rows: int = 200_000  # connection rows before aggregation
    queries: int = 256  # distinct source x target pairs
    operations: int = 5_000_000
    candidate_removals: int = 10_000  # across all queries and thresholds
    removal_operations: int = 2_000_000  # removal BFS pops and adjacency visits
    seconds: float = 30.0
    report_bytes: int = 8 * 1024 * 1024  # each artifact
    witness_nodes: int = 100_000  # all reported paths, including repetitions

    def validate(self):
        import math
        for name, ceiling in asdict(Limits()).items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise AuditError(f"invalid limit: {name}")
            if not math.isfinite(value) or not 0 < value <= ceiling:
                raise AuditError(f"{name} must be > 0 and <= {ceiling}")
            if name != "seconds" and not isinstance(value, int):
                raise AuditError(f"{name} must be an integer")


class Budget:
    def __init__(self, limits, clock=time.monotonic):
        limits.validate()
        self.limits = limits
        self.clock = clock
        self.deadline = clock() + limits.seconds
        self.operations = 0
        self.witness_nodes = 0

    def tick(self, count=1):
        self.operations += count
        if self.operations > self.limits.operations:
            raise LimitError("computation operation limit exhausted")
        self.check()

    def check(self):
        if self.clock() >= self.deadline:
            raise LimitError("runtime limit exhausted")

    def witness(self):
        self.witness_nodes += 1
        if self.witness_nodes > self.limits.witness_nodes:
            raise LimitError("total witness-node limit exhausted")
        self.tick()


def analyze(graph, sources, targets, thresholds, budget):
    """One BFS per source and threshold; one parent per node, no path enumeration.

    Sorted adjacency + FIFO BFS yields the lexicographically first shortest
    path by Unicode code point sequence. Synapse counts gate edges, not costs.
    """
    from .ingest import identifier
    sources, targets = sorted(set(sources)), sorted(set(targets))
    for node in sources + targets:
        identifier(node)
    if not sources or not targets:
        raise AuditError("at least one source and target are required")
    if len(sources) * len(targets) > budget.limits.queries:
        raise LimitError("query pair limit exhausted")
    if not thresholds or len(thresholds) > 12:
        raise AuditError("provide 1 to 12 distinct thresholds")
    if any(type(t) is not int or not 1 <= t <= MAX_COUNT for t in thresholds):
        raise AuditError("thresholds must be positive safe integers")
    if len(set(thresholds)) != len(thresholds):
        raise AuditError("duplicate thresholds are not allowed")
    thresholds = sorted(thresholds)
    queries = [{"source": s, "target": t} for s in sources for t in targets]
    results, summaries = [], []
    for threshold in thresholds:
        adjacency = {}
        retained = 0
        for (source, target), count in sorted(graph.edges.items()):
            budget.tick()
            if count >= threshold:
                adjacency.setdefault(source, []).append(target)
                retained += 1
        reachable = missing = 0
        for source in sources:
            parent = {source: None} if source in graph.nodes else {}
            todo = deque(parent)
            while todo:
                budget.tick()
                node = todo.popleft()
                for neighbor in adjacency.get(node, ()):
                    budget.tick()
                    if neighbor not in parent:
                        parent[neighbor] = node
                        todo.append(neighbor)
            for target in targets:
                budget.tick()
                result = {"source": source, "target": target, "threshold": threshold,
                          "status": "no_path_in_supplied_graph", "hops": None,
                          "path": [], "edge_counts": [], "bottleneck": None,
                          "missing_ids": []}
                absent = [n for n in dict.fromkeys((source, target)) if n not in graph.nodes]
                if absent:
                    result.update(status="missing_node", missing_ids=absent)
                    missing += 1
                elif target in parent:
                    path = []
                    node = target
                    while node is not None:
                        budget.witness()
                        path.append(node)
                        node = parent[node]
                    path.reverse()
                    counts = [graph.edges[a, b] for a, b in zip(path, path[1:])]
                    result.update(status="reachable", hops=len(path) - 1, path=path,
                                  edge_counts=counts, bottleneck=min(counts) if counts else None)
                    reachable += 1
                results.append(result)
        summaries.append({"threshold": threshold, "retained_edges": retained,
                          "removed_edges": len(graph.edges) - retained,
                          "reachable_pairs": reachable, "missing_pairs": missing,
                          "no_path_pairs": len(queries) - reachable - missing})
    return {"thresholds": thresholds, "queries": queries, "summaries": summaries,
            "results": results}
