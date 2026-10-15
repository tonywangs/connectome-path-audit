"""Strict version-1 CSV and provenance contracts. Read and hash identical bytes."""
import csv
from dataclasses import dataclass
import hashlib
import io
import json
import os
import re
import stat
import unicodedata

from .core import AuditError, LimitError, MAX_COUNT


@dataclass
class Graph:
    nodes: dict
    edges: dict
    rows: int
    duplicate_rows: int
    self_loop_edges: int
    inputs: dict
    provenance: dict


def identifier(value):
    if (not isinstance(value, str) or not value or len(value) > 256
            or value != value.strip() or any(unicodedata.category(c).startswith("C") for c in value)):
        raise AuditError("IDs must be nonempty strings of <=256 characters without outer whitespace or control characters")
    return value


def label(value):
    if (not isinstance(value, str) or len(value) > 512
            or any(unicodedata.category(c).startswith("C") for c in value)):
        raise AuditError("labels must be <=512 characters without control characters")
    return value


def read_regular(path, remaining, budget):
    # O_NONBLOCK avoids hanging on a FIFO before fstat; symlinked regular inputs
    # are permitted. Hash is over bytes actually read, not a second file read.
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise AuditError("inputs must be regular local files")
        chunks, size = [], 0
        while True:
            budget.check()
            chunk = stream.read(min(65536, remaining - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > remaining:
                raise LimitError("combined input byte limit exhausted")
            chunks.append(chunk)
        data = b"".join(chunks)
    return data, {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def csv_rows(data, header):
    try:
        text = data.decode("utf-8-sig")
        # newline='' preserves quoted CR/LF; identifier/label policy rejects them.
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        if next(reader, None) != header:
            raise AuditError(f"CSV header must be exactly {','.join(header)}")
        for row in reader:
            if len(row) != len(header):
                raise AuditError(f"CSV record ending at line {reader.line_num}: expected {len(header)} fields")
            yield row
    except (UnicodeError, csv.Error) as exc:
        raise AuditError(f"invalid UTF-8 CSV: {exc}") from exc


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def provenance_from_bytes(data):
    try:
        meta = json.loads(data, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise AuditError("invalid provenance JSON") from exc
    keys = {"schema", "kind", "dataset", "revision", "license", "attribution", "selection", "limitations"}
    if not isinstance(meta, dict) or set(meta) != keys:
        raise AuditError("provenance requires exactly: " + ", ".join(sorted(keys)))
    if meta["schema"] != "connectome-provenance/v1":
        raise AuditError("unsupported provenance schema")
    if meta["kind"] not in ("synthetic", "public", "private", "unknown"):
        raise AuditError("invalid provenance kind")
    for key in keys - {"limitations"}:
        if not isinstance(meta[key], str) or not meta[key].strip() or len(meta[key]) > 2048:
            raise AuditError(f"provenance {key} must be a nonempty string <=2048 characters")
    if (not isinstance(meta["limitations"], list) or not 1 <= len(meta["limitations"]) <= 16
            or any(not isinstance(s, str) or not s.strip() or len(s) > 2048 for s in meta["limitations"])):
        raise AuditError("provenance limitations requires 1..16 nonempty strings <=2048 characters")
    return meta


def load_graph(connections, nodes, provenance, budget):
    inputs, content = {}, {}
    used = 0
    for role, path in (("connections", connections), ("nodes", nodes), ("provenance", provenance)):
        if path is None:
            continue
        data, info = read_regular(path, budget.limits.input_bytes - used, budget)
        inputs[role] = info
        content[role] = data
        used += len(data)
    meta = provenance_from_bytes(content["provenance"])
    node_map, edges = {}, {}
    def add_node(node):
        if node not in node_map:
            if len(node_map) >= budget.limits.nodes:
                raise LimitError("node limit exhausted")
            node_map[node] = ""
    if nodes is not None:
        for node, name in csv_rows(content["nodes"], ["node_id", "label"]):
            budget.tick()
            identifier(node)
            label(name)
            if node in node_map:
                raise AuditError("duplicate node ID in nodes CSV")
            add_node(node)
            node_map[node] = name
    rows = duplicates = 0
    for source, target, raw_count in csv_rows(content["connections"], ["source", "target", "synapses"]):
        budget.tick()
        rows += 1
        if rows > budget.limits.rows:
            raise LimitError("connection row limit exhausted")
        identifier(source)
        identifier(target)
        if len(raw_count) > 16 or not re.fullmatch(r"[1-9][0-9]*", raw_count):
            raise AuditError("synapses must be canonical positive decimal integers")
        count = int(raw_count)
        add_node(source)
        add_node(target)
        key = source, target
        if key in edges:
            duplicates += 1
        elif len(edges) >= budget.limits.edges:
            raise LimitError("distinct edge limit exhausted")
        total = edges.get(key, 0) + count
        if total > MAX_COUNT:
            raise AuditError("aggregated synapse count exceeds maximum safe integer")
        edges[key] = total
    return Graph(node_map, edges, rows, duplicates,
                 sum(a == b for a, b in edges), inputs, meta)
