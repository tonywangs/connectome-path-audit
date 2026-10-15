# Existing capabilities and semantic differences

Reviewed 2026-10-15. This project does not claim a new pathway algorithm.

[FlyWire Codex FAQ](https://codex.flywire.ai/faq) describes directed presynaptic-to-postsynaptic connections, pair-total thresholds, region-separated connection rows, and shortest non-empty pathways. It lists FAFB's default cutoff as five synapses, with dataset-specific minima. Codex supports pathway graphs and downloadable path-length matrices. Its snapshot and filtering boundaries matter when interpreting missing paths.

This tool audits local supplied CSVs across multiple cutoffs, recording exact byte hashes and deterministic witnesses. It allows thresholds from one but cannot restore upstream-omitted connections. Unlike Codex's documented non-empty pathway semantics, a present self-query here has zero hops. It has no cell-type queries, avoid-query filters, 3D rendering, live proofreading access, or biological simulation.

The independent reference is **NetworkX 3.4.2**, pinned in `requirements-verify.txt`. Reviewed the [tagged unweighted shortest-path implementation](https://github.com/networkx/networkx/blob/networkx-3.4.2/networkx/algorithms/shortest_paths/unweighted.py), including single-source distances and bidirectional search. The [shortest-path reference](https://networkx.org/documentation/stable/reference/algorithms/shortest_paths.html) explains unweighted hop distance and directed traversal. Verification uses a `DiGraph` and unweighted distances, with isolates explicitly inserted. The installed implementation's SHA-256 is recorded in `results/verification.json`; no NetworkX code is copied into production.

The test suite independently builds reference edges from original generated records and compares all query distances. A separate Floyd–Warshall matrix provides an algorithmically different check on the small seeded graphs. Witness ties are checked using independently computed distances to the target, rather than assuming NetworkX's returned witness uses the same tie-break.
