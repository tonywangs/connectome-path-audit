# Connectome Path Audit

An offline connectivity-table-to-report workflow for comparing directed reachability across synapse-count thresholds. It preserves exact neuron IDs, records source hashes and provenance, and shows a deterministic shortest witness with counts for every edge.

**Try the included [interactive synthetic report](results/example/report.html)** by opening it locally in a browser. Nothing is deployed. The report needs no server, account, or network access.

## Run an audit

Python 3.10+; no runtime dependencies. From a checkout:

```sh
PYTHONPATH=src python3 -m connectome_audit examples/connections.csv \
  --nodes examples/nodes.csv --provenance examples/provenance.json \
  --source sensor --target motor --target isolated --target sensor --target absent \
  --thresholds 1,5,6,9,10 --output /tmp/my-connectome-audit
```

The output directory must not already exist; its parent must exist. Open `/tmp/my-connectome-audit/report.html`. The bundle also contains deterministic `report.json` and a `COMPLETE.json` marker with artifact hashes. Treat a directory without that marker as incomplete.

To install the CLI into an environment with the build prerequisites available:

```sh
python3 -m pip install --no-build-isolation --no-deps .
connectome-audit --help
```

For a fully offline install, prepare a wheel on a machine with `setuptools==75.8.0` and `wheel==0.45.1`, then install that local wheel with `pip install --no-index --no-deps path/to/wheel.whl`. The verification command below exercises this process in a fresh environment, outside the checkout.

### What the example demonstrates

The fixture is entirely synthetic, including its numeric-looking identifier.

| Minimum synapses | sensor → motor | Deterministic witness |
| --- | --- | --- |
| 1 or 5 | 2 hops | sensor → fast → motor |
| 6 or 9 | 3 hops | sensor → relay-a → relay-b → motor |
| 10 | No path in supplied graph | None |

Two `sensor → fast` rows sum to 5 **before** thresholding. A tied short route exists; the lexicographically first shortest node sequence wins. The isolated cell is explicitly declared. A source queried against itself has a zero-hop identity path; an absent ID is unresolved, even when source and target are equal.

## Bring your own local data

Connections use the exact UTF-8 CSV header `source,target,synapses`. IDs remain strings; counts are positive integers. An optional `node_id,label` CSV adds labels and isolates. A required provenance JSON records dataset, revision, license, attribution, selection boundaries, and limitations. See the [versioned input/output contract](docs/contract.md) and [example provenance](examples/provenance.json).

Repeat `--source` and `--target` for their Cartesian product, up to 256 pairs, and select up to 12 thresholds. The CLI performs breadth-first searches; it never enumerates all paths. In the HTML, select a threshold, filter query IDs or labels, inspect a query, compare it across cutoffs, and page through its witness edges. Query and edge tables mount at most 20 rows each; every finding remains reachable. Native buttons/selects support keyboard navigation. The JSON download contains the exact adjacent JSON bytes.

This tool does not fetch, normalize, or infer undocumented upstream data. Raw FlyWire exports need an explicit conversion to this contract; retain upstream selection and filtering information in provenance. Public-data acquisition was attempted but did not provide a connectivity file without account access. This release therefore includes only synthetic data; see [acquisition evidence and dependency](docs/public-data.md).

## Verify

Prepare development dependencies once (requires network access or a prepopulated wheelhouse):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-verify.txt
.venv/bin/python -m playwright install chromium
```

If the platform lacks the `venv`/`ensurepip` component, install that Python distribution component or use an existing Python virtual environment. Chromium's system libraries must also be available. Runtime use of the CLI does not require Playwright, NetworkX, pip, or Chromium.

Then run **one verification command**, offline:

```sh
.venv/bin/python scripts/verify.py
```

Use `PLAYWRIGHT_BROWSERS_PATH` if the browser cache is elsewhere. The verifier requires Linux and GNU `/usr/bin/time` for per-process RSS measurements. It never downloads anything. It runs failure tests and independent graph checks, builds and installs a wheel in an isolated environment, forbids network sockets in Python child processes, checks inputs are unchanged and repeated output bytes match, and exercises Chromium with external networking blocked. It writes only to temporary directories unless `--record` is supplied.

Actual recorded evidence is in [results/verification.json](results/verification.json), [results/tests.log](results/tests.log), and [the results explanation](docs/validation.md). It includes 300 seeded graphs checked against pinned NetworkX 3.4.2 and an independent Floyd–Warshall matrix, with every witness checked. The larger seeded workload adds 1,024 independently checked findings. These are software correctness checks, not biological validation.

## Interpretation and boundaries

“No path” means **no directed path in this supplied graph at this threshold**, not biological disconnection. Omitted cells, omitted edges, upstream thresholds, and proofreading errors can change reachability. Lowering a threshold cannot restore data never supplied. Counts gate edges; they are not traversal costs, probabilities, signs, delays, or measures of causality.

Wiring paths do not establish signal propagation, causal influence, engineered dynamics, or consciousness. The tool does not simulate neuronal activity or offer physiological or clinical validation.

Resource ceilings are explicit and can only be lowered. Any input error, exhausted baseline limit, serialization failure, or caught cancellation fails the whole audit, rather than fabricating “no path” findings. See [limits and failure semantics](docs/contract.md#limits-and-failure-semantics). The CLI and report make no external requests. Report files contain the supplied IDs, labels, and provenance; handle them according to the sensitivity of your inputs.

FlyWire Codex already provides pathway exploration. This project's scope is a reproducible offline threshold audit, with no novelty claim. See [existing work and semantic differences](docs/existing-work.md).

Code and synthetic fixtures: [MIT license](LICENSE).

## Audit individual connection failures

Add `--single-edge-failure` to any existing audit command:

```sh
PYTHONPATH=src python3 -m connectome_audit examples/connections.csv \
  --nodes examples/nodes.csv --provenance examples/provenance.json \
  --source sensor --target motor --target isolated --target sensor --target absent \
  --thresholds 1,5,6,9,10 --single-edge-failure --output /tmp/connection-failures
```

Open the [synthetic failure report](results/edge-failure-example/report.html), select a query and threshold, then inspect candidate removals and paginated alternative paths. At threshold 5, redundant routes preserve sensor → motor after either baseline edge is removed. At threshold 6, all three edges of its remaining route are individually critical. At threshold 10, the query is initially unreachable, distinct from removal-induced disconnection.

Each trial removes an **entire aggregated directed edge**, not one synapse or CSV row. Any individually critical edge must lie on the baseline witness; removing an edge outside it leaves that witness intact. Alternatives include replayable node sequences and synapse counts. Self-loops cannot be critical; a present self-query retains its zero-hop path.

The extension is versioned `connectome-single-edge-failure/v1`. `--max-candidate-removals` (10,000) and `--max-removal-operations` (2,000,000) bound work across all queries and thresholds. Exhausting either produces explicit unresolved candidates and a **partial** analysis, including in the HTML. The outer completion marker certifies a finished bundle; inspect the extension status before treating the critical-edge list as exhaustive. Runtime, total-work, witness and output limits still abort the bundle. See the [full contract](docs/contract.md#optional-connectome-single-edge-failurev1).

Criticality is specific to this source, target, threshold and supplied graph. Edge removal is a graph operation, not a validated neuronal intervention or a measure of biological importance. Missing connections can change every conclusion.

The same single verification command above covers this extension, including 300 additional seeded graphs checked by removing every retained edge in an independent NetworkX reference. Current evidence is in [edge-failure-verification.json](results/edge-failure-verification.json); the original reachability evidence and example remain historical artifacts.

## Audit individual intermediate-node failures

```sh
PYTHONPATH=src python3 -m connectome_audit examples/node-failure/connections.csv \
  --nodes examples/node-failure/nodes.csv --provenance examples/node-failure/provenance.json \
  --source sensor --target motor --target sensor --target isolated --target absent \
  --thresholds 1,5,6 --single-node-failure --single-edge-failure \
  --output /tmp/node-failures
```

Open the [shared-node synthetic report](results/node-failure-example/report.html)
locally. At threshold 1 a weak bypass avoids the shared node. At threshold 5,
two input branches and two output branches provide edge redundancy: no individual
edge disconnects sensor → motor, yet removing `shared` does. At threshold 6 the
query is initially unreachable. This distinguishes edge redundancy from
intermediate-node redundancy without inferring biological importance.

`--single-node-failure` removes a node and all incoming/outgoing edges in each
independent trial. Endpoints are excluded. Only intermediate nodes on the
baseline path need testing; deleting any other eligible node preserves that
path. Identity and direct paths have no intermediate candidates. Inspect node
outcomes and paginated alternative witnesses in the new HTML section.

Both failure flags are optional and can be used separately or together. Together,
edge trials run first and node trials use the remaining shared removal budgets.
Unresolved trials are shown explicitly; check each extension's completeness
before treating its critical list as exhaustive. The enclosing bundle marker
only certifies that the report finished writing. See the
[node-failure contract](docs/contract.md#optional-connectome-single-node-failurev1).

The same `scripts/verify.py` command now checks node failures, preserving earlier
edge and baseline regression coverage. Current measurements and checks are in
[node-failure-verification.json](results/node-failure-verification.json) and
[node-failure-tests.txt](results/node-failure-tests.txt). `--record` refreshes only
these new artifacts and the node example; earlier evidence and examples remain
historical. Node deletion is a graph operation, **not a validated neuronal
intervention**. All included examples are synthetic.

## Find critical intermediates with dominators

Use `--dominator-node-failure` to share a bounded dominator computation across
all targets with the same source and threshold. It classifies intermediates
without repeated node-removal searches. Add `--dominator-witnesses` only when
alternative paths are needed:

```sh
PYTHONPATH=src python3 -m connectome_audit examples/node-failure/connections.csv \
  --nodes examples/node-failure/nodes.csv \
  --provenance examples/node-failure/provenance.json \
  --source sensor --target motor --target sensor --target isolated --target absent \
  --thresholds 1,5,6 --dominator-node-failure --dominator-witnesses \
  --output /tmp/dominator-audit
```

Open the [complete example](results/dominator-example/report.html). At threshold
5, `shared` is a critical intermediate for sensor → motor. At threshold 1, a
bypass makes it noncritical. Identity, initially unreachable and missing-ID queries
remain distinct. The HTML shows algorithm provenance, classification completeness,
and witness availability, with keyboard controls and paginated tables.

`--max-dominator-operations` (2,000,000) and
`--max-dominator-source-operations` (250,000) bound tree construction and ancestor
walks. Exhaustion produces unresolved classifications. Optional witnesses have
separate `--max-dominator-witness-searches` (10,000) and
`--max-dominator-witness-operations` (2,000,000) ceilings. Witness exhaustion does
not invalidate completed classifications. All extensions still consume the shared
hard runtime, operation, witness-node and output limits; those failures abort the
bundle. Existing removal options retain their behavior and may be combined.

See [semantics, algorithm and measured tradeoffs](docs/dominators.md) and
[reproducible evidence](results/dominator-verification.json). The same
`scripts/verify.py` command runs all historical regressions, independent dominator
checks, offline installed-CLI and browser workflows, and six balanced paired
benchmark repetitions. `--record` now writes new dominator artifacts and preserves
all earlier result files. These are synthetic graph checks; graph-node removal
is **not a validated neuronal intervention**.
