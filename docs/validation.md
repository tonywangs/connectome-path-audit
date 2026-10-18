# Validation and measured results

These are executed software checks on synthetic data, not physiological validation or a biological discovery. The original 1.0.0 measurements and file fingerprints are in [`results/verification.json`](../results/verification.json); plain unit-test output is in [`results/tests.log`](../results/tests.log). Run `python scripts/verify.py` in the prepared verification environment to repeat the full workflow; add `--record` to refresh the latest node-failure evidence described below. Earlier evidence is preserved.

## Correctness

- 19 test methods passed, including invalid UTF-8/CSV/provenance, malformed counts, duplicate aggregation overflow, missing IDs, isolates, cycles, self-loops, tied paths, large identifiers, exact cutoff boundaries, exactly 12 thresholds, and safe-integer maximum counts.
- 300 seeds (0–299), 145,458 findings and 42,874 reachable witnesses checked. Distances agree with NetworkX 3.4.2 and a separately implemented Floyd–Warshall matrix. Every reachable witness is checked for endpoints, hops, unique nodes, directed edges, counts, cutoff inclusion, weakest edge, and deterministic lexicographic tie-break. Reachability/distance monotonicity is checked across increasing thresholds. Periodic reversed input-row/query order checks agree.
- The 2,000-node benchmark adds 1,024 findings checked against NetworkX from independently aggregated raw records.
- Byte-identical full bundles across repeated isolated CLI processes with different Python hash seeds; unchanged input hashes. The fixture's sensor-to-motor hop sequence is `[2, 2, 3, 3, null]` at thresholds `[1, 5, 6, 9, 10]`. The null is explicitly a supplied-graph no-path result.
- Byte/node/edge/row/query/work/witness/runtime/report ceilings are exercised. Serialization errors, output collisions (including an existing empty directory and symlink), injected disk failures at each artifact fsync, and real SIGINT/SIGTERM during output writing leave no newly completed bundle. FIFO inputs are rejected without blocking. Tests verify bounded runtime interruption on Linux.

## Installed offline workflow

The verifier copies source to a clean temporary build directory, builds a wheel without an index or build isolation, creates a separate virtual environment without pip, installs the local wheel through the verification environment's pip, and invokes the installed console command from outside the checkout. Package import location is checked. A `sitecustomize` guard rejects network socket connection/DNS use in Python child processes (including build/install); zero attempts were observed. This is an application-level network guard, not a claim of an OS network namespace.

| Workload | Elapsed seconds | Peak process RSS (KiB) | JSON bytes | HTML bytes |
| --- | ---: | ---: | ---: | ---: |
| Installed example: 8 nodes, 11 rows, 4 pairs, 5 thresholds | 0.173916 | 20452 | 7022 | 26648 |
| Seed 1701: 2,000 nodes, 10,000 rows, 256 pairs, 4 thresholds | 0.935433 | 26168 | 330461 | 350087 |
| Same benchmark repeated | 0.783090 | 26436 | identical | identical |

Elapsed time includes child process startup and filesystem I/O. GNU `time` measures each child's maximum resident set size; Python is included. These are individual observations, not confidence intervals, throughput guarantees, or measurements of all limit-sized inputs. The full verification took 19.761718 seconds on this run. Environment: Python 3.12.3, Linux-6.8.0-124-generic-x86_64-with-glibc2.39, 4 reported CPUs. Exact dependency versions, input hashes, artifact hashes/sizes, and verified-source hashes are recorded in the machine-readable result.

## Browser

Chromium 134.0.6998.35, Playwright 1.51.0, local `file:` report, offline browser context plus request interception. Zero external request attempts and zero JavaScript errors. Checks exercised all 68 query rows and all 64 hops of a long witness, with at most 20 mounted rows per paged table; threshold selection by overview buttons and select; status and label filters; previous/next queries across page boundaries; native keyboard activation; focus after inspection; and 1280×960 and 360×800 viewports. Narrow-screen tables scroll within their containers without whole-document overflow. Hostile markup and literal escape/template sequences remain inert. The downloaded JSON matches the original artifact byte-for-byte.

Desktop and narrow layouts were also visually inspected. Native semantics, captions, headings, focus indicators and labeled controls are included, but no screen-reader study, automated WCAG conformance audit, or cross-browser/device certification is claimed. JavaScript-disabled readers are directed to the JSON.

## Negative results and limits

The synthetic path disappears above its supporting counts exactly as expected. It is not biological disconnection. An unauthenticated public-data acquisition attempt returned a landing page, so no real-data accuracy or redistribution claims are made; see [the acquisition record](public-data.md). Full FlyWire-scale graphs exceed the deliberate local bounds. Runtime timers cannot preempt uninterruptible kernel I/O, and a force kill may leave an uncommitted directory. No network, paid compute, physiological simulation, or inference service is needed to run these audits.


## Single-edge failure extension (1.1.0)

The historical 1.1.0 run is recorded separately in [edge-failure-verification.json](../results/edge-failure-verification.json) and [edge-failure-tests.txt](../results/edge-failure-tests.txt). Original results/verification.json, results/tests.log, and results/example remain unchanged historical evidence. Run `python scripts/verify.py` in the pinned verification environment for the full offline check; `--record` now refreshes the 1.2.0 node evidence and example; the edge artifacts below remain historical.

All 28 tests passed, including inherited CLI collision, serialization, write-failure, runtime and real SIGINT/SIGTERM cleanup tests with the failure option enabled. The original 300-seed reachability oracle remains. The additional seeds 81000–81299 generate 300 directed graphs, with duplicate rows independently aggregated, cycles, self-loops, isolates, missing endpoints, large string IDs and threshold boundaries. Exhaustive reference deletion tested 5,764 retained edges across graph/threshold combinations; all ordered query pairs produced 69,136 findings, 10,449 critical findings and 6,415 independently verified alternative witnesses. Reference BFS is NetworkX 3.4.2; candidate selection is never used to restrict the reference deletions. Separate fixed cases cover twelve thresholds, tied routes, aggregate deletion, identity queries and exhausted limits.

The installed CLI was built and installed offline in a fresh environment and run outside the checkout, with Python network sockets forbidden. Repeated examples and the failure workload were byte-identical under different hash seeds, and source hashes were unchanged. Every alternative in those installed complete bundles was independently checked too. The partial example was checked for visible unresolved outcomes in Chromium. No external request attempts or JavaScript errors were observed.

The bounded failure workload has 92 nodes, 91 edges, 68 query pairs and 3 thresholds. It attempted 4,163 candidate removals with 411,948 traversal operations in 1.002376 seconds, using 30,720 KiB peak process RSS (GNU time; CLI process, not browser RSS). JSON was 846,303 bytes; HTML was 871,432 bytes. The browser visited 64 candidate rows and all 89 edges of a long alternative; no paginated table mounted more than 20 rows. Its measured inspection DOM had 736 elements. Exact dependency versions, input hashes, source fingerprints, browser version and runtime measurements are in the evidence JSON.

These are modest synthetic correctness workloads, not connectome-scale performance claims. Runtime measurements vary by machine/load and include process startup. Two removal-specific ceilings yield partial results, while global runtime, operation, witness and artifact ceilings abort publication of the bundle. A completed bundle can contain unresolved candidates, so consumers must inspect the extension completeness status. The analysis does not establish biological function or validate neuronal interventions; missing connections can change every conclusion.


## Single-node failure extension (1.2.0)

Executed evidence is in [node-failure-verification.json](../results/node-failure-verification.json)
and [node-failure-tests.txt](../results/node-failure-tests.txt). Earlier JSON,
test output, and example bundles remain unchanged historical artifacts. The
single offline command is `python scripts/verify.py` in the pinned environment;
`--record` refreshes only the node evidence and example.

All 44 tests passed. The original reachability and edge-failure checks still
run. The node reference uses seeds 91000–91299 to generate 300 directed graphs.
For each threshold it copies the independently aggregated graph and calls
NetworkX 3.4.2 `remove_node` for every supplied node, including isolates and nodes
outside the baseline witness. Endpoints are excluded separately for each query.
Across 7,768 graph/threshold/node deletions and 70,544 query findings, the
reference agrees on all 6,050 critical findings. Every one of the 1,498
alternative witnesses is independently checked for node avoidance, directed
edges, counts, shortest distance and canonical tie-breaking. Fixed regressions
cover endpoint exclusions, identity and direct paths, loops, cycles, duplicate
rows, tied routes, 12 thresholds, missing IDs, disconnected graphs, shared
edge/node limits, hard runtime/work/witness limits, and unchanged graphs and
baseline findings. Node-only and combined flags both run the inherited collision,
serialization, output-size, write-failure, cancellation and cleanup regressions,
including real SIGINT/SIGTERM during writing.

Fresh installed CLI runs outside the source tree cover both flags and node-only
analysis, with Python child networking forbidden. Complete installed node
bundles are independently compared to deletion of every node; every alternative
is replayed. Inputs stay byte-identical, and repeated examples, node workload
and partial benchmark bundles match byte-for-byte under different hash seeds.

| Installed workload | Elapsed seconds | Peak process RSS (KiB) | JSON bytes | HTML bytes |
| --- | ---: | ---: | ---: | ---: |
| Shared-node example, both flags: 10 nodes / 13 edges / 4 pairs / 3 thresholds | 0.170696 | 20,608 | 12,052 | 39,836 |
| Chain and detour: 92 nodes / 92 edges / 68 pairs / 3 thresholds | 1.055127 | 28,544 | 700,087 | 727,871 |
| Seed 1701, partial: 2,000 nodes / 9,995 edges / 256 pairs / 4 thresholds | 1.631633 | 36,028 | 1,200,186 | 1,227,970 |

The complete chain/detour workload starts 4,032 node trials and counts 400,260
removal traversal operations. The larger benchmark intentionally lowers limits
to 20 trial starts and 100,000 traversal operations. It reports `partial`, with
19 resolved candidates (19 verified alternatives) and 4,987 explicitly unresolved
candidates. Every resolved trial is independently replayed on a copied NetworkX
graph; unresolved records have no witness or disconnection claim. This is a
negative completeness result at these chosen limits, not evidence that the
remaining nodes disconnect or preserve the query.

Network-blocked Chromium 134.0.6998.35 checks all 68 query rows, 63 intermediate
candidates for the longest query, and all 88 edges of its node-avoiding detour.
No paginated evidence table mounts more than 20 rows; the inspected node
candidate/alternative view had 710 DOM elements. Separate partial and combined
reports verify visible unresolved outcomes, independent inspector selections,
identity/missing-ID states and empty filters. Keyboard activation, focus after
inspection, thresholds, labels, pagination, narrow viewport and exact JSON
download are exercised. Hostile labels in candidate and alternative nodes remain
inert text. There were zero external request attempts and zero JavaScript
errors. The node inspector was also visually inspected. These are not a
screen-reader study or cross-browser accessibility certification.

Measurements use GNU time for peak **CLI process** RSS, not browser memory;
elapsed includes process startup. The full verification took
69.96433 seconds on this run. Exact environment, dependency versions,
input/source hashes, graph sizes and artifact sizes are recorded in the JSON.
Individual observations are not throughput guarantees or full-limit stress
measurements. The benchmark is synthetic and much smaller than full connectomes.

The two-diamond example has no individually critical edge at threshold 5, but
`shared` is an individually critical intermediate node. A weak bypass at
threshold 1 removes that criticality; at threshold 6 the baseline is already
unreachable. This is a reproducible graph distinction, not a biological finding.
Node removal is not a validated neuronal intervention; no physiological data,
cell silencing/ablation validation or real-data accuracy claim is included.
