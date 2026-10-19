#!/usr/bin/env python3
"""Recreate the documented induced subgraph from a pinned public source archive."""
import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'examples/larva/upstream/elife-83739-fig1-data1-v2.zip'
URL = 'https://cdn.elifesciences.org/articles/83739/elife-83739-fig1-data1-v2.zip'
SHA256 = 'c92177b4720d86b210ea44c10b9354fdf079c8cca88f0c0bce3b57815293c9cb'
GROUPS = ['KCs', 'MB-FBNs', 'MBINs', 'MBONs']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode()


def csv_bytes(header, rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode()


def extract(archive):
    raw = Path(archive).read_bytes()
    if digest(raw) != SHA256:
        raise ValueError('Source archive SHA-256 mismatch; refusing a different dataset')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        edges_raw = z.read('elife/G_edgelist.txt')
        meta_raw = z.read('elife/meta_data.csv')
    metadata = list(csv.DictReader(io.StringIO(meta_raw.decode('utf-8'))))
    if len({r[''] for r in metadata}) != len(metadata):
        raise ValueError('Duplicate upstream neuron identifiers')
    selected = {r['']: r for r in metadata if r['simple_group'] in GROUPS}
    edges = {}
    upstream_rows = 0
    for line in edges_raw.decode('utf-8').splitlines():
        a, b, value = line.split()
        count = Decimal(value)
        if not count.is_finite() or count <= 0 or count != count.to_integral_value():
            raise ValueError('Upstream weights must be positive integral synapse counts')
        upstream_rows += 1
        if a in selected and b in selected:
            if (a, b) in edges:
                raise ValueError('Unexpected duplicate upstream pair')
            edges[a, b] = int(count)
    outputs = {
        'connections.csv': csv_bytes(['source', 'target', 'synapses'],
                                     ((a, b, w) for (a, b), w in sorted(edges.items()))),
        'nodes.csv': csv_bytes(['node_id', 'label'],
                              ((n, f"{r['name']} | {r['simple_group']} | {r['hemisphere']}")
                               for n, r in sorted(selected.items()))),
        'annotations.json': json_bytes([{'id': n, 'name': r['name'],
                                         'group': r['simple_group'], 'hemisphere': r['hemisphere']}
                                        for n, r in sorted(selected.items())]),
    }
    provenance = {
        'schema': 'connectome-provenance/v1', 'kind': 'public',
        'dataset': 'Larval Drosophila mushroom-body-related induced subgraph (eLife 83739 Figure 1 source data 1)',
        'revision': 'elife-83739-fig1-data1-v2; article version 2, 2023-03-28',
        'license': 'CC BY 4.0, eLife article and Figure 1 source data; https://creativecommons.org/licenses/by/4.0/; see examples/larva/NOTICE.md',
        'attribution': 'Winding et al. (2023), The connectome of an insect brain, doi:10.1126/science.add9330; source data published with Pedigo et al. (2023), doi:10.7554/eLife.83739. ' + URL,
        'selection': 'scripts/import_larva.py selects metadata simple_group in KCs, MB-FBNs, MBINs, MBONs, both hemispheres, and every G_edgelist edge with both endpoints selected. No count cutoff or other cell filter. Preserve original skeleton IDs as strings, self-loops and isolated selected cells; first column is source, second target, third summed synapse count. Sort IDs lexicographically. Source ZIP SHA-256: ' + SHA256,
        'limitations': [
            'This induced subgraph omits every neuron outside four published groups and all incident edges. It is not the complete mushroom body or whole brain. Missing paths do not establish biological disconnection.',
            'G is the upstream sum across axon/dendrite compartment connection types. Counts are structural contacts, not signs, strengths, probabilities, delays, activity, or causal influence.',
            'One larval specimen and a historical reconstruction/annotation snapshot; proofreading, developmental and annotation limitations remain. Labels are upstream annotations, not independently validated cell identities.',
            'Deleting graph nodes is not a validated neuronal intervention. There is no neural dynamics simulation, physiological validation, or inference about biological function.',
        ],
    }
    outputs['provenance.json'] = json_bytes(provenance)
    manifest = {
        'schema': 'connectome-source/v1', 'url': URL, 'archive_sha256': SHA256,
        'archive_bytes': len(raw), 'article_doi': '10.7554/eLife.83739',
        'source_members': {name: {'sha256': digest(b), 'bytes': len(b)} for name, b in
                           [('elife/G_edgelist.txt', edges_raw), ('elife/meta_data.csv', meta_raw)]},
        'selection_groups': GROUPS, 'upstream_metadata_rows': len(metadata),
        'upstream_edge_rows': upstream_rows, 'selected_nodes': len(selected),
        'selected_edges': len(edges), 'selected_synapses': sum(edges.values()),
        'selected_self_loops': sum(a == b for a, b in edges),
        'output_files': {name: {'sha256': digest(b), 'bytes': len(b)} for name, b in outputs.items()},
    }
    outputs['source-manifest.json'] = json_bytes(manifest)
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ARCHIVE)
    parser.add_argument('--output', type=Path, default=ROOT / 'examples/larva')
    parser.add_argument('--check', action='store_true', help='Compare with existing files; write nothing')
    args = parser.parse_args()
    outputs = extract(args.archive)
    if not args.check:
        args.output.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        if args.check:
            if (args.output / name).read_bytes() != content:
                raise ValueError(f'Stale extraction: {name}')
        else:
            (args.output / name).write_bytes(content)
    print(json.dumps({'files': len(outputs), 'source_sha256': SHA256, 'check': args.check}))


if __name__ == '__main__':
    main()
