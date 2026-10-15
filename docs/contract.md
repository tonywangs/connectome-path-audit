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

For a present self-query, status is reachable, `hops=0`, `path=[source]`, counts empty, bottleneck null. A missing self-query remains unresolved. Null hops alone is not a status. There is no incomplete-status finding: the CLI fails without committing a report if the entire computation cannot finish.

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
