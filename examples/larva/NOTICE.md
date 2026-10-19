# Public source data and attribution

The archive `upstream/elife-83739-fig1-data1-v2.zip` is **Figure 1—source data 1,
Drosophila larva brain connectome**, published with:

Benjamin D. Pedigo, Mike Powell, Eric W. Bridgeford, Michael Winding, Carey E.
Priebe, and Joshua T. Vogelstein (2023). *Generative network modeling reveals
quantitative definitions of bilateral symmetry exhibited by a whole insect brain
connectome*. eLife 12:e83739. <https://doi.org/10.7554/eLife.83739>.

The original reconstruction is credited to Michael Winding and colleagues (2023).
*The connectome of an insect brain*. Science 379:eadd9330.
<https://doi.org/10.1126/science.add9330>.

## Terms

The eLife article and its Figure 1 source-data supplement are distributed under
**Creative Commons Attribution 4.0 International (CC BY 4.0)**:
<https://creativecommons.org/licenses/by/4.0/>. Credit the authors and source,
link the license, and indicate modifications. This dataset is not relicensed
under this project's MIT code license. No endorsement by the authors is implied.

The publisher's [article metadata](https://api.elifesciences.org/articles/83739)
identifies article version 2 and the
[article XML](https://cdn.elifesciences.org/articles/83739/elife-83739-v2.xml)
contains the CC BY 4.0 license and `fig1sdata1` supplement reference. The data are
available as a direct, account-free [publisher download](https://cdn.elifesciences.org/articles/83739/elife-83739-fig1-data1-v2.zip).
Acquired and inspected on 2026-10-19. The original archive is preserved byte for
byte; hashes and member sizes are in `source-manifest.json`.

## Modifications and identifiers

`../../scripts/import_larva.py` converts the upstream weighted edge list to
`source,target,synapses` CSV. It selects all metadata rows whose `simple_group`
is `KCs`, `MB-FBNs`, `MBINs`, or `MBONs`, and all edges between those neurons.
The groups are Kenyon cells, mushroom-body feedback neurons, input neurons,
and output neurons, using the source annotations. Both hemispheres, selected
isolates, and self-loops are retained. No developmental, reconstruction-quality,
hemisphere, count, or largest-component filter is applied. It is **not** the
preprocessed/binarized hemisphere graph used for the eLife statistical analysis.

The metadata's unnamed first column and the first two edge-list fields are
original neuron skeleton identifiers, preserved as decimal **strings**. Names,
groups, and hemisphere labels come directly from the upstream metadata; no
labels are inferred. These are larval reconstruction IDs, not FlyWire adult root
IDs. Numeric-looking IDs are not renumbered or converted to browser numbers.

The author's [pinned loader](https://github.com/neurodata/bilateral-connectome/blob/4482b9022f27d361011c9c7442e32ca51d607d08/pkg/pkg/data/load_data.py)
reads the edge-list columns as source, target, weight into a directed graph.
It calls `G` the `sum` graph. The accompanying
[data definition](https://github.com/neurodata/bilateral-connectome/blob/4482b9022f27d361011c9c7442e32ca51d607d08/scripts/define_data.py)
describes the four axon/dendrite compartment types. We use the supplied summed
weights, require positive integral values, and preserve the source → target
orientation. We do not infer excitatory/inhibitory signs or simulate activity.

The full source metadata has 3,591 rows; its edge list has 119,010 rows. Those
source-file universes include annotations beyond the paper's headline brain
neuron count. Do not substitute a published whole-brain count for these actual
file counts. The selected 408-neuron graph contains 18,431 directed edges and
63,486 synapses; these are descriptive counts, not biological validation.

`connections.csv`, `nodes.csv`, `annotations.json`, and `provenance.json` are
derived files. `source-manifest.json` records their hashes and the exact selection.
The archive SHA-256 is
`c92177b4720d86b210ea44c10b9354fdf079c8cca88f0c0bce3b57815293c9cb`.

## Reproduce offline

From the project root, `python3 scripts/import_larva.py --check` checks the
archive hash and re-extracts all derived bytes in memory for comparison.
`python3 scripts/import_larva.py --output /tmp/larva-inputs` writes a fresh copy.
To reacquire the archive, download the publisher URL above and supply its local
path with `--archive`; a different SHA-256 is rejected. No network or account is
needed to use the included copy.
