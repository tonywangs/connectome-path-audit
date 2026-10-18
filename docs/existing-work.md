# Existing capabilities and semantic differences

Reviewed 2026-10-15. This project does not claim a new pathway algorithm.

[FlyWire Codex FAQ](https://codex.flywire.ai/faq) describes directed presynaptic-to-postsynaptic connections, pair-total thresholds, region-separated connection rows, and shortest non-empty pathways. It lists FAFB's default cutoff as five synapses, with dataset-specific minima. Codex supports pathway graphs and downloadable path-length matrices. Its snapshot and filtering boundaries matter when interpreting missing paths.

This tool audits local supplied CSVs across multiple cutoffs, recording exact byte hashes and deterministic witnesses. It allows thresholds from one but cannot restore upstream-omitted connections. Unlike Codex's documented non-empty pathway semantics, a present self-query here has zero hops. It has no cell-type queries, avoid-query filters, 3D rendering, live proofreading access, or biological simulation.

The independent reference is **NetworkX 3.4.2**, pinned in `requirements-verify.txt`. Reviewed the [tagged unweighted shortest-path implementation](https://github.com/networkx/networkx/blob/networkx-3.4.2/networkx/algorithms/shortest_paths/unweighted.py), including single-source distances and bidirectional search. The [shortest-path reference](https://networkx.org/documentation/stable/reference/algorithms/shortest_paths.html) explains unweighted hop distance and directed traversal. Verification uses a `DiGraph` and unweighted distances, with isolates explicitly inserted. The installed implementation's SHA-256 is recorded in `results/verification.json`; no NetworkX code is copied into production.

The test suite independently builds reference edges from original generated records and compares all query distances. A separate Floyd–Warshall matrix provides an algorithmically different check on the small seeded graphs. Witness ties are checked using independently computed distances to the target, rather than assuming NetworkX's returned witness uses the same tie-break.

## Directed single-edge failure analysis

Reviewed 2026-10-15:

- Abdol-Hossein Esfahanian, [Connectivity Algorithms](https://www.cse.msu.edu/~cse835/Papers/Graph_connectivity_revised.pdf), section 2 and Algorithm 1, defines directed local edge connectivity through arc deletion and gives a unit-capacity flow reduction. This supplies the mathematical context, not physiological validation.
- NetworkX [local_edge_connectivity](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.connectivity.connectivity.local_edge_connectivity.html) and its [implementation](https://networkx.org/documentation/stable/_modules/networkx/algorithms/connectivity/connectivity.html) compute a minimum cut cardinality with auxiliary directed networks and maximum flow. The verification dependency remains pinned to NetworkX 3.4.2; live documentation may describe a later version.

This extension reports every individually disconnecting edge for each reachable ordered query, not just one minimum cut or its size. A fixed baseline witness bounds candidates: any edge outside it can be removed without destroying that witness. Repeated BFS after suppressing each candidate yields either an alternative path or an exhausted-search result. This elementary reduction is not a novelty claim. Flow-based local connectivity provides useful context, while independent exhaustive edge deletion supplies the test oracle. General directed strong bridges, undirected bridges, and biological importance are different questions.

## Directed single-node failure analysis

Reviewed 2026-10-18:

- Esfahanian, [Connectivity Algorithms](https://www.cse.msu.edu/~cse835/Papers/Graph_connectivity_revised.pdf),
  section 4, defines local vertex deletion with the two endpoints excluded and
  describes reduction to flow by splitting intermediate vertices. This provides
  graph-theoretic context; its global connectivity problem and conventions for
  adjacent endpoints are not the output of this tool.
- NetworkX [DiGraph.remove_node](https://networkx.org/documentation/stable/reference/classes/generated/networkx.DiGraph.remove_node.html)
  removes the vertex and incident edges. Verification uses this operation on a
  copied graph for **every** node, then excludes each query's endpoints. This is
  independent of the production candidate restriction and traversal suppression.
- NetworkX [minimum_st_node_cut](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.connectivity.cuts.minimum_st_node_cut.html)
  uses an auxiliary flow network to find a minimum separating set. This audit
  instead lists all individually disconnecting nodes and gives explicit
  alternative witnesses or unresolved outcomes under work limits.
- NetworkX's [dominance implementation](https://networkx.org/documentation/stable/_modules/networkx/algorithms/dominance.html)
  is another relevant approach: dominators describe vertices shared by all paths
  from a start vertex. This extension chooses repeated bounded BFS for simple,
  replayable alternatives and explicit interruption semantics, rather than
  implementing a dominator tree. Undirected articulation points are not a
  substitute for ordered-query reachability in a digraph.

The fixed-witness candidate restriction is elementary: deleting a node outside
an existing path leaves that path intact. No algorithmic novelty is claimed.
Live documentation may describe newer NetworkX versions; tests remain pinned
to 3.4.2 and record hashes of the installed reference sources. Neither these
references nor the synthetic experiments validate a neuronal intervention.
