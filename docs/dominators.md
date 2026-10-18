# Bounded critical intermediate nodes

The opt-in dominator extension uses directed aggregated edges with synapse count
at least the selected threshold. A node is critical for an initially reachable
source/target pair exactly when every directed source-to-target path contains
it. Source and target are excluded. Missing IDs are unresolved baseline inputs;
initially unreachable targets have no removal-induced disconnection claim.
A present source equal to target has a zero-hop path and no critical intermediates.
Self-loops and cycles are allowed. Duplicate rows are summed before thresholding.

Classification is separate from witness construction. Only intermediate nodes on
the baseline path need explicit classification: removing any other eligible node
preserves that baseline path. A converged immediate-dominator tree gives the
critical nodes as the target's ancestors, excluding endpoints. An unconverged
tree supplies no classifications. Bounded work may produce unresolved results;
hard global runtime/memory/output failures produce no completed bundle.

The implementation follows the engineered iterative algorithm (Figure 3) in
Cooper, Harvey and Kennedy, [A Simple, Fast Dominance Algorithm](https://www.cs.tufts.edu/~nr/cs257/archive/keith-cooper/dom14.pdf).
Its postorder intersection walks predecessor dominator chains to a common ancestor.
This is established compiler graph analysis, not a novel algorithm. The independently
installed [NetworkX 3.4.2 implementation](https://github.com/networkx/networkx/blob/networkx-3.4.2/networkx/algorithms/dominance.py)
is pinned in requirements-verify.txt; validation also deletes every eligible node
individually. No NetworkX runtime dependency is introduced.

Graph-node removal is not a validated neuronal intervention. Missing connections,
selection boundaries and upstream errors can change every classification.

## Resource and output contract

The opt-in JSON extension is `dominator_node_failure`, schema
`connectome-dominator-node-failure/v1`. The baseline `connectome-audit/v1` and both
older failure extensions remain supported. Each result has `status`,
`classification_complete`, `critical_nodes`, ordered baseline `candidates`, and
`untested_noncritical_nodes` (nodes certified by the unchanged baseline path).
Candidates have `status` (`critical`, `noncritical`, `unresolved`) and independent
`witness_status` (`available`, `not_requested`, `not_applicable`, `unresolved`).
Empty `critical_nodes` with incomplete classification is not a claim of robustness.
Missing and initially unreachable queries have no applicable classification;
aggregate `status` indicates computational completion, not baseline reachability.

Each source/threshold gets a fresh 250,000-operation allowance, inside a shared
2,000,000-operation allowance. DFS steps, rank construction, sweep nodes,
predecessor visits, dominator-chain steps and target ancestor steps are charged.
A tree is used only after fixed-point convergence. If a target ancestor walk
exhausts its allowance, its whole candidate classification is unresolved, without
publishing a partial critical set. Trees are discarded after each source group,
so storage is linear in graph size, plus bounded output. There is no recursion.
Threshold adjacency construction, grouping and serialization consume the global
hard budget. The global five-million-operation and 30-second ceilings also apply.

No alternate paths are constructed by default. Requested witnesses use up to
10,000 BFS searches and 2,000,000 operations, separately from classification and
older removal extensions. BFS steps, reconstruction and replay are charged;
all reconstructed nodes additionally consume the shared 100,000 witness-node
ceiling. Returned alternatives are replayed against the retained edges and removed
node; independent tests also check shortest distance. No partial witness is emitted.
Hard limits or cancellation abort the entire bundle, including earlier completed
classifications, using the existing transactional writer.

The reference PDF retrieved from the Tufts academic mirror has SHA-256
`2454168c21a1dfeeb5ab91a1057a94964cd722c7109e0afd3c5da630527fe232`.
The installed NetworkX dominance module hash is recorded in verification evidence.

## Reproduce measurements

`benchmarks/dominator-suite.json` was frozen before candidate timing. Its SHA-256
is `66cf60b5d97b686b288c391ad7827f78cb040475945c35998f529641bf39df95`.
`PYTHONPATH=src python3 scripts/dominator_benchmark.py` runs it with six repetitions
per method and case. The order alternates removal/classification/witness mode and
its reverse, balancing each method's position. Inputs and thresholds are identical
within pairs. Every worker is a fresh process. Elapsed time measures the extension
only; GNU time maximum RSS includes interpreter, imports, input construction and
baseline. Traversal counters describe algorithm-specific steps, not equivalent CPU
instructions. The harness records hard-limit failures as entirely unresolved,
including diagnostic traversal counts from unwound frames and no partial output.

Removal searches construct alternatives as part of their existing contract.
Classification-only dominators do less work. The third mode requests alternatives
to expose their cost. No warmup, outlier removal or hardware isolation is applied;
these bounded synthetic measurements are not a claim about real connectomes.
The frozen diamond case may exceed the hard witness-node limit in witness-producing
methods; failures remain part of the suite. Exact agreement is required for all
classifications completed by both methods, and full-output agreement is recorded
separately. Timing a failed or partial run is not timing an equivalent completed task.

## Recorded results

The recorded Linux run passed 56 tests, including 300 seeded directed graphs, 69,030 findings,
6,828 exhaustive reference node removals and 4,000 independently verified alternate
witnesses. The installed example, repeatability, cleanup, cancellation, and offline
Chromium workflows passed. Chromium exercised 63 dominator candidate rows and 88
alternative edges with filtering, pagination, keyboard focus, hostile labels,
missing queries, and separate absent/exhausted witness states. Python children and
Chromium recorded zero external network attempts. Full machine details, raw trials,
input hashes and source fingerprints are in [the evidence](../results/dominator-verification.json).

Median extension seconds over six balanced repetitions (R = removal, D = dominator
classification only, W = dominator with requested witnesses):

| Case | R seconds | D seconds | W seconds | R / D completed candidates |
| --- | ---: | ---: | ---: | ---: |
| chain-shared | 1.609414 | 0.037018 | 0.039877 | 7992 / 7992 |
| chain-single | 0.079833 | 0.006176 | 0.005759 | 356 / 356 |
| dense-single | 0.008533 | 0.025608 | 0.022876 | 1 / 1 |
| diamonds-shared | 0.848295 | 0.023659 | 0.770342 | 0 / 5344 |
| random-shared | 0.124152 | 0.038853 | 0.150274 | 158 / 158 |
| budget-exhaustion | 0.021927 | 0.023082 | 0.022334 | 9 / 0 |

The dense single-query case is slower with dominators: computing an entire tree
can cost more than the few removal searches required. Requested witnesses also
add overhead on the random shared-source workload. The 100-operation case resolves
9 of 7,992 candidates with removal but zero with dominators: tree convergence
is an all-or-nothing prerequisite. Neither outcome is called complete.

On the diamond case, classification-only dominators complete 5,344 candidates.
Both witness-producing methods hit the hard witness-node ceiling and emit no
completed report; their timings are failure times, not completed-task speedups.
The harness counts all 5,344 candidates unresolved for those failed runs. All
classifications completed by both methods agree exactly, and the four fully
completed workloads have identical classification outputs in every repetition.

Peak process RSS medians (KiB; includes baseline and interpreter):

| Case | Removal | Dominators | Dominators + witnesses |
| --- | ---: | ---: | ---: |
| chain-shared | 24832 | 25216 | 25472 |
| chain-single | 20864 | 20736 | 20800 |
| dense-single | 21176 | 21240 | 21166 |
| diamonds-shared | 24320 | 24064 | 24320 |
| random-shared | 20992 | 20992 | 21056 |
| budget-exhaustion | 24896 | 24896 | 24896 |

Runtime ratios are workload-specific observations. The suite is small and synthetic;
differences in interpreter overhead and host load can affect timings. No biological
validation, neuronal intervention equivalence or universal performance advantage is
claimed. Historical result bundles and evidence remain unchanged.
