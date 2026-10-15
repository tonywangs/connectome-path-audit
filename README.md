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

Resource ceilings are explicit and can only be lowered. Any input error, exhausted limit, serialization failure, or caught cancellation fails the whole audit, rather than fabricating “no path” findings. See [limits and failure semantics](docs/contract.md#limits-and-failure-semantics). The CLI and report make no external requests. Report files contain the supplied IDs, labels, and provenance; handle them according to the sensitivity of your inputs.

FlyWire Codex already provides pathway exploration. This project's scope is a reproducible offline threshold audit, with no novelty claim. See [existing work and semantic differences](docs/existing-work.md).

Code and synthetic fixtures: [MIT license](LICENSE).
