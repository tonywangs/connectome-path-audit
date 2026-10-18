# Input and output contracts

## `connectome-csv/v1`

The JSON report identifies this input contract. Version 1 has two CSV formats:

| File | Required header, exactly and in order |
| --- | --- |
| Connections | `source,target,synapses` |
| Optional nodes | `node_id,label` |

Files are local regular files, decoded as UTF-8 (an initial BOM is accepted). Comma delimiter, double-quote escaping, LF or CRLF line endings. CSV quoting permits commas/quotes in IDs or labels. Blank records, extra/missing fields, wrong headers, invalid UTF-8, and malformed quoted fields are rejected. Connection rows are counted before aggregation. A header-only connections file is valid.

IDs are nonempty strings of at most 256 Unicode code points, without leading/trailing whitespace or Unicode category C characters (controls, formatting, surrogates, private-use, unassigned). Case, leading zeroes, and Unicode normalization are preserved. `001`, `1`, and `720575940628731140` are distinct strings; no floating-point conversion occurs. Numeric-looking IDs in spreadsheet software must be imported as text before exporting to this tool.

Labels are optional empty strings or text up to 512 code points, with the same category C exclusion. Labels do not affect paths. IDs and labels may contain markup-like characters, which are displayed as text. Embedded CR/LF and tabs are rejected. Duplicate node-table IDs are rejected, even if labels match. Every connection endpoint is added to the node set; the nodes file is supplementary, not an allowlist. A listed node without an edge is an explicit isolate. An unlisted and unconnected query ID is missing, not an isolate.

Synapse counts use canonical decimal `[1-9][0-9]*`, at most 9,007,199,254,740,991. Zero, negatives, spaces, signs, leading zeroes, decimals, exponents, and non-ASCII digits are rejected. The sum for a directed pair must also fit this bound, ensuring exact JavaScript integer representation.

Repeated `(source,target)` rows are **summed before thresholding**. This supports disjoint counts from separate regions, but will double-count accidentally repeated exports: the caller must ensure records represent distinct contributions. The tool reports duplicate-row counts but cannot detect duplicated observations. A reciprocal pair consists of two different directed edges. Self-loops are retained and included in edge statistics; they do not make a shortest identity path nonzero.

## `connectome-provenance/v1`

Required local JSON object, with exactly these keys (duplicate JSON keys are errors):

| Key | Meaning |
| --- | --- |
| `schema` | Exactly `connectome-provenance/v1` |
| `kind` | `synthetic`, `public`, `private`, or `unknown` |
| `dataset` | Dataset name |
| `revision` | Immutable upstream revision or a declared local revision |
| `license` | License, restrictions, or an explicit statement that rights are unknown |
| `attribution` | Authors and source citation/URL as appropriate |
| `selection` | How this graph was selected, including region boundaries and upstream filters |
| `limitations` | 1–16 nonempty strings describing omissions and interpretation limits |

Other than the limitations list, values are nonempty strings up to 2,048 characters. List entries have the same maximum length. Values are declarations supplied by the caller, not verified biological claims or license determinations. Revision/selection text is required even when the honest value is “unknown”; hash provenance allows detection of changes. The tool computes SHA-256 over the actual bytes it reads for each input role, including BOM/line endings. Paths, timestamps, hostnames, and measured runtimes are excluded from the deterministic report.

## Query and graph semantics

Sources and targets are explicit repeated flags. Duplicates are removed; each set is sorted by Unicode code point order. The result covers their Cartesian product. Thresholds are 1–12 distinct positive integers within the synapse-count bound, normalized into ascending numeric order. Leading zeroes in CLI thresholds are accepted as decimal; duplicate numeric thresholds are rejected. A directed edge is retained exactly when its aggregate count is **greater than or equal to** the threshold. The node set does not change as edges are removed.

Breadth-first search gives the minimum number of directed edges. Sorted adjacency and FIFO expansion select the lexicographically smallest shortest node sequence. This is not a strongest-path optimizer; a path's weakest edge is reported only as evidence. One BFS per source per threshold stores one parent per visited node, then reconstructs queried witnesses. It neither enumerates paths nor builds a combinatorial set of shortest-path ties. Query results are ordered by threshold, source, target. Excluding sorting and witness materialization, work is O(T × S × (V + E)); searches can stop only via a whole-audit failure, never a partial “no path” result.

## `connectome-audit/v1`

`report.json` is ASCII JSON with sorted object keys, compact separators, a final newline, and `<`, `>`, `&` escaped. The HTML embeds these same bytes, and its download returns them unchanged. Reports include schema/tool versions, `status: complete`, input hashes/byte sizes, declared provenance, graph statistics, sorted node labels, semantics, configured limits, operation/witness counts, queries, threshold summaries, and findings.

Each finding contains `source`, `target`, `threshold`, `status`, `hops`, `path`, `edge_counts`, `bottleneck`, and `missing_ids`:

| Status | Meaning and payload |
| --- | --- |
| `reachable` | Endpoints exist and a directed witness exists. `hops` is an integer; `path` includes both endpoints; each `edge_counts[i]` supports `path[i] → path[i+1]`. |
| `no_path_in_supplied_graph` | Both endpoints exist and exhaustive BFS found no path at this threshold. `hops`/`bottleneck` are null; paths/counts empty. |
| `missing_node` | One or both endpoints are absent from the entire supplied node set; `missing_ids` identifies them. No reachability claim; `hops`/`bottleneck` null, paths/counts empty. |

For a present self-query, status is reachable, `hops=0`, `path=[source]`, counts empty, bottleneck null. A missing self-query remains unresolved. Null hops alone is not a status. Baseline findings are never partial: the CLI fails without committing a report if baseline computation cannot finish. The optional removal extension has separate partial outcomes described below.

Threshold summaries distinguish retained/removed aggregated edges (including loops), reachable pairs, no-path pairs, and missing-ID pairs. Increasing the threshold cannot create reachability or shorten a path; witnesses can change when edges disappear.

## Limits and failure semantics

All default limits are hard application ceilings; `--max-*` options may only lower them.

| Resource | Default / ceiling | Flag |
| --- | --- | --- |
| Combined raw input bytes | 8 MiB | `--max-input-bytes` |
| Unique nodes | 10,000 | `--max-nodes` |
| Aggregated directed edges | 100,000 | `--max-edges` |
| Raw connection rows | 200,000 | `--max-rows` |
| Source × target pairs | 256 | `--max-queries` |
| Distinct thresholds | 12 | Enforced on `--thresholds` |
| Counted operations | 5,000,000 | `--max-operations` |
| Elapsed seconds | 30 | `--max-seconds` |
| Each serialized report artifact | 8 MiB | `--max-report-bytes` |
| Total nodes across all witness paths | 100,000 | `--max-witness-nodes` |

Counted operations include parsed rows, edge filtering, BFS node expansion and neighbor inspection, result construction, and each reconstructed witness node. They are a conservative deterministic work metric, not CPU instructions. Input size, node count, and runtime bound uncounted work such as sorting and serialization. Limits bound data structures; there is no separate OS memory limit. On POSIX, a wall-clock timer interrupts Python execution; cooperative checks also run during reading, graph work, serialization, and writing. Python signal handling cannot guarantee termination during uninterruptible kernel I/O; on systems without `setitimer`, runtime checks are cooperative. Only Linux has been measured here.

Exit code 0 means a completed bundle; 2 means invalid input, I/O/serialization error, or limit exhaustion; 130 means caught SIGINT/SIGTERM cancellation. Argument parser errors also exit 2. Errors explicitly state `INCOMPLETE`; no unknown finding is encoded as absence of a path. The writer never overwrites existing output directories, files, or symlinks, even empty directories. Inputs are opened read-only. Serialize both reports before creating output. Exclusive directory creation reserves the destination; files are exclusively created, flushed, and fsynced, with `COMPLETE.json` written last. Caught failures remove created files and the reserved directory.

A force kill or power loss can leave an uncommitted directory; require the completion marker and verify its hashes before consuming a bundle. Directory metadata is not fsynced, so this is not a power-loss-durable transaction. Output should be on a local filesystem with an existing parent directory; concurrent adversarial mutation of that directory is outside the contract. An existing stale output must be inspected/removed or a different output path selected by the caller; no automatic replacement occurs.

The self-contained HTML disables network/resource loads with a restrictive Content Security Policy, uses text nodes for input-derived content, and paginates query/witness tables. It is not a general HTML editor. JavaScript is required for interactivity; without it, the notice directs the reader to the adjacent complete JSON.

## Optional `connectome-single-edge-failure/v1`

`--single-edge-failure` adds a versioned `single_edge_failure` object at the document level and a same-named object on each baseline finding. Baseline findings, threshold comparisons, ordering, and the input contract retain their meanings. The document object records the removal unit, candidate strategy, analysis completeness, total attempted removals, and counted removal traversal work. Input hashes, provenance, limits and settings remain in the enclosing document. No network or additional data source is used.

For a reachable source–target query at threshold t, an edge is **critical** if deleting that entire retained aggregated directed pair makes the target unreachable from the source. Each trial starts from the original thresholded graph; failures are not cumulative. Synapse counts are not capacities. Deleting one duplicate CSV row or decrementing a count is a different operation and is not implemented. Reciprocal edges are distinct.

Every critical edge belongs to the deterministic baseline witness: if an edge is outside that path, deleting it leaves the path intact. Testing each edge on the witness therefore identifies **all** individually critical edges when the candidate analysis is complete. `untested_noncritical_edges` counts other retained edges, including self-loops; the unchanged baseline is a reusable witness for their removals. This is not enumeration of all minimum cuts, nor analysis of combinations of failures. A present self-query has an empty candidate list, zero critical edges, and a zero-hop path preserved under every edge removal. A self-loop cannot be individually critical under these reachability semantics.

Per-query fields include `candidate_count`, ordered `candidates`, `critical_edges`, `untested_noncritical_edges`, and status:

| Query status | Meaning |
| --- | --- |
| `complete` | Every candidate classified; confirmed critical list is exhaustive. |
| `partial` | At least one candidate unresolved; confirmed critical list is a lower bound, never an exhaustive claim. |
| `initially_unreachable` | Baseline already has no path; no removal-induced disconnection is claimed. |
| `missing_node` | Baseline endpoints missing; no removal analysis. |

Candidates follow baseline path order. Each stores `edge: [from,to]`, original aggregate `synapses`, `status`, `reason`, `path`, `edge_counts`, `search_complete`, and `visited_nodes`:

| Candidate status | Evidence |
| --- | --- |
| `alternative_path` | Canonical shortest path avoiding the removed pair, with counts replayed against the supplied graph. Search stops after finding a path; `search_complete` is false. |
| `disconnected` | BFS exhausted its queue without reaching the target; `search_complete` is true and `visited_nodes` records the full reachable-set size. No path payload. |
| `unresolved` | Candidate or removal-traversal budget exhausted; explicit `reason`, no witness or disconnection claim, null visited count. Includes trials that could not start. |

The extension's overall status is `partial` if any query is partial; otherwise `complete` (missing endpoints and initially unreachable queries remain explicitly distinguished). `tested_removals` counts searches started, including interrupted searches. The report's outer `status: complete` and bundle marker mean that serialization finished, not that all removal trials resolved. Consumers must check the extension status. Exit code 0 can therefore accompany a partial analysis; the CLI prints that status separately.

Two additional ceilings may only be lowered:

| Resource, across all queries/thresholds | Ceiling | Flag | Exhaustion |
| --- | --- | --- | --- |
| Candidate searches started | 10,000 | `--max-candidate-removals` | Remaining candidates unresolved |
| Removal BFS pops + neighbor inspections | 2,000,000 | `--max-removal-operations` | Current and remaining candidates unresolved |

The existing 5,000,000 total-operation, 30-second runtime, 100,000 witness-node and 8 MiB per-artifact limits still apply to the entire workflow, including alternatives. Their exhaustion aborts the bundle, as do cancellation and serialization errors. Only the two additional ceilings permit a partial report. Each candidate search costs O(V + E) in the worst case, with O(V + E) search memory; total work is bounded by the explicit budgets. Paths and unresolved records also consume bounded output space. The HTML paginates candidate and alternative-edge tables at 20 rows, including partial outcomes.

Edge removal is a graph operation, **not a validated neuronal intervention**. Query-relative criticality does not establish biological importance. Missing connections can change every conclusion.

## Optional `connectome-single-node-failure/v1`

`--single-node-failure` adds `single_node_failure` to the document and each
finding. It uses the same offline inputs, bounded Cartesian queries, and up to
12 thresholds. The original baseline and edge-failure meanings are unchanged.

Each trial removes **one node and all incident incoming/outgoing edges**, including
self-loops, from the original thresholded graph. Trials are independent, never
cumulative. Source and target are excluded even when they coincide. A present
self-query preserves its zero-hop identity path and has no candidates; a direct
source-to-target edge likewise survives every eligible node removal. A missing
endpoint remains `missing_node`, and a previously unreachable query remains
`initially_unreachable`: neither supports a removal-induced disconnection claim.

Only `path[1:-1]` of the deterministic baseline witness needs testing. For any
eligible node outside that path, the unchanged baseline witnesses continued
reachability. Therefore complete candidate analysis identifies **all individually
critical intermediate nodes**, including in cyclic directed graphs. This does not
find combinations of failures, enumerate minimum cuts, or measure global graph
connectivity. Isolates and off-path nodes are covered by the unchanged witness,
not by extra searches. Endpoints are not counted as noncritical.

The per-query object contains:

- `status`: `complete`, `partial`, `initially_unreachable`, or `missing_node`.
- `candidate_count` and `candidates`: intermediate baseline nodes in path order.
- `critical_nodes`: confirmed disconnecting node IDs, in candidate order. This is
  exhaustive only when query status is `complete`; otherwise it is a lower bound.
- `untested_noncritical_nodes`: for reachable queries, the number of supplied
  nodes outside the path and excluded endpoints. Their removal preserves the
  baseline. For other statuses this is zero and makes no noncriticality claim.

Each candidate has `node` (the exact string ID), `status`, `reason`, `path`,
`edge_counts`, `search_complete`, and `visited_nodes`. Labels are resolved from
the enclosing sorted `nodes` array; hashes and declared provenance are in the
same document. Candidate status and evidence follow the edge extension:
`alternative_path` includes a replayed canonical shortest witness avoiding the
node; `disconnected` requires an exhausted BFS and `search_complete: true`;
`unresolved` carries a limit reason, empty witness, false search completeness,
and null visited count. A verified alternative does not require an exhaustive
reachable-set search, so its `search_complete` remains false.

The versioned document object records removal semantics, endpoint policy,
identity behavior, candidate strategy, completeness, `tested_removals`, and
`traversal_operations`. Node counters describe node trials only.
`prior_edge_removals` and `prior_edge_traversal_operations` record the edge work
already charged. When both flags are present, **edge trials run first**, then
node trials use the remaining shared `--max-candidate-removals` and
`--max-removal-operations` allowances. Flag order does not change this order.
A node-only run receives the full allowances. Standalone edge runs retain their
existing limits and behavior. One extension can be complete while the other is
partial; inspect each separately.

The removal ceilings (10,000 starts and 2,000,000 BFS pops/neighbor inspections)
apply across all queries, thresholds, and both requested extensions. Exhausting
them yields explicit partial outcomes. Global operation, runtime, witness and
output limits still abort the entire bundle. There is no silent truncation.
Worst-case per-trial search is O(V + E), with O(V + E) search memory; paths and
candidate records also consume bounded report space. The CLI prints the node
extension status. A completed bundle and exit 0 do not imply all removals resolved.

The HTML has separate node and edge inspectors, each with at most 20 candidate
or alternative-edge rows mounted per page. Filtering or changing the selected
query updates both inspectors; keyboard buttons and focus targets expose all
pages. Input labels are displayed as text, including removal and witness labels.

Node removal is a **graph operation, not a validated neuronal intervention**.
No claim about cell ablation, silencing, compensation, dynamics, physiological
function, or biological importance follows from these results. Missing
connections can change every conclusion.

## Optional dominator extension

`--dominator-node-failure` adds `connectome-dominator-node-failure/v1` fields without
replacing baseline or removal-extension fields. `--dominator-witnesses` requires
that flag and requests separately budgeted alternatives. See the
[complete semantics and limit contract](dominators.md#resource-and-output-contract).
