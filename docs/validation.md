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
