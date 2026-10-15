# Validation and measured results

These are executed software checks on synthetic data, not physiological validation or a biological discovery. Machine-readable measurements and file fingerprints are in [`results/verification.json`](../results/verification.json); plain unit-test output is in [`results/tests.log`](../results/tests.log). Run `python scripts/verify.py` in the prepared verification environment to repeat the full workflow; add `--record` to refresh evidence.

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

The current run is recorded separately in [edge-failure-verification.json](../results/edge-failure-verification.json) and [edge-failure-tests.txt](../results/edge-failure-tests.txt). Original results/verification.json, results/tests.log, and results/example remain unchanged historical evidence. Run `python scripts/verify.py` in the pinned verification environment for the full offline check; `--record` refreshes only the extension evidence and example.

All 28 tests passed, including inherited CLI collision, serialization, write-failure, runtime and real SIGINT/SIGTERM cleanup tests with the failure option enabled. The original 300-seed reachability oracle remains. The additional seeds 81000–81299 generate 300 directed graphs, with duplicate rows independently aggregated, cycles, self-loops, isolates, missing endpoints, large string IDs and threshold boundaries. Exhaustive reference deletion tested 5,764 retained edges across graph/threshold combinations; all ordered query pairs produced 69,136 findings, 10,449 critical findings and 6,415 independently verified alternative witnesses. Reference BFS is NetworkX 3.4.2; candidate selection is never used to restrict the reference deletions. Separate fixed cases cover twelve thresholds, tied routes, aggregate deletion, identity queries and exhausted limits.

The installed CLI was built and installed offline in a fresh environment and run outside the checkout, with Python network sockets forbidden. Repeated examples and the failure workload were byte-identical under different hash seeds, and source hashes were unchanged. Every alternative in those installed complete bundles was independently checked too. The partial example was checked for visible unresolved outcomes in Chromium. No external request attempts or JavaScript errors were observed.

The bounded failure workload has 92 nodes, 91 edges, 68 query pairs and 3 thresholds. It attempted 4,163 candidate removals with 411,948 traversal operations in 1.002376 seconds, using 30,720 KiB peak process RSS (GNU time; CLI process, not browser RSS). JSON was 846,303 bytes; HTML was 871,432 bytes. The browser visited 64 candidate rows and all 89 edges of a long alternative; no paginated table mounted more than 20 rows. Its measured inspection DOM had 736 elements. Exact dependency versions, input hashes, source fingerprints, browser version and runtime measurements are in the evidence JSON.

These are modest synthetic correctness workloads, not connectome-scale performance claims. Runtime measurements vary by machine/load and include process startup. Two removal-specific ceilings yield partial results, while global runtime, operation, witness and artifact ceilings abort publication of the bundle. A completed bundle can contain unresolved candidates, so consumers must inspect the extension completeness status. The analysis does not establish biological function or validate neuronal interventions; missing connections can change every conclusion.
