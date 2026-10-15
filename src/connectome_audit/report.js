'use strict';
(() => {
  const data = JSON.parse(document.getElementById('audit-data').textContent);
  const $ = id => document.getElementById(id);
  const labels = new Map(data.nodes.map(n => [n.id, n.label]));
  const size = 20;
  let threshold = data.thresholds[0], page = 0, selected = 0, hopPage = 0;
  let filtered = [];
  const statusText = {reachable: 'Reachable', no_path_in_supplied_graph: 'No path in supplied graph', missing_node: 'Missing ID — unresolved'};
  const rows = new Map(data.thresholds.map(t => [t, data.results.filter(r => r.threshold === t)]));
  const display = id => labels.get(id) ? `${id} · ${labels.get(id)}` : id;
  function element(tag, value, parent) {
    const el = document.createElement(tag);
    if (value !== undefined && value !== null) el.textContent = String(value);
    if (parent) parent.append(el);
    return el;
  }
  function cell(row, value) { return element('td', value, row); }
  function nodeCell(row, id) {
    const td = cell(row, id);
    if (labels.get(id)) element('small', labels.get(id), td);
  }
  function dash(value) { return value === null ? '—' : value; }
  function drawSummary() {
    const body = $('summary').tBodies[0];
    for (const s of data.summaries) {
      const tr = element('tr', null, body);
      const button = element('button', `≥ ${s.threshold}`, cell(tr));
      button.dataset.threshold = s.threshold;
      button.setAttribute('aria-label', `Select threshold ${s.threshold}`);
      button.addEventListener('click', () => { $('threshold').value = String(s.threshold); changeThreshold(); });
      for (const k of ['retained_edges', 'removed_edges', 'reachable_pairs', 'no_path_pairs', 'missing_pairs']) cell(tr, s[k]);
    }
  }
  function drawPairs() {
    const query = $('filter').value.toLocaleLowerCase();
    const status = $('status').value;
    filtered = rows.get(threshold).map((r, index) => ({r, index})).filter(({r}) =>
      (status === 'all' || r.status === status) &&
      (display(r.source) + ' ' + display(r.target)).toLocaleLowerCase().includes(query));
    const pages = Math.max(1, Math.ceil(filtered.length / size));
    page = Math.min(page, pages - 1);
    if (!filtered.some(f => f.index === selected)) {
      selected = filtered.length ? filtered[0].index : -1;
      hopPage = 0;
    }
    const body = $('pairs').tBodies[0]; body.replaceChildren();
    for (const {r, index} of filtered.slice(page * size, (page + 1) * size)) {
      const tr = element('tr', null, body);
      tr.setAttribute('aria-selected', String(selected === index));
      nodeCell(tr, r.source); nodeCell(tr, r.target);
      cell(tr, statusText[r.status]); cell(tr, dash(r.hops));
      const button = element('button', selected === index ? 'Selected' : 'Inspect', cell(tr));
      button.setAttribute('aria-label', `Inspect ${r.source} to ${r.target}`);
      button.addEventListener('click', () => { selected = index; hopPage = 0; drawPairs(); $('path-heading').focus(); });
    }
    if (!filtered.length) { const td = cell(element('tr', null, body), 'No matching queries. Clear the filter or choose another result type.'); td.colSpan = 5; }
    $('filter-count').textContent = `${filtered.length} of ${data.queries.length} query pairs · threshold ≥ ${threshold}`;
    $('page-label').textContent = `Page ${page + 1} of ${pages}`;
    $('previous-page').disabled = page === 0; $('next-page').disabled = page >= pages - 1;
    document.querySelectorAll('#summary button').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.threshold) === threshold)));
    drawPath();
  }
  function drawPath() {
    drawFailures();
    const pos = filtered.findIndex(f => f.index === selected);
    $('previous-query').disabled = pos <= 0;
    $('next-query').disabled = pos < 0 || pos >= filtered.length - 1;
    const body = $('path').tBodies[0]; body.replaceChildren();
    const compare = $('query-comparison').tBodies[0]; compare.replaceChildren();
    if (selected < 0) {
      $('selected-pair').textContent = 'No query selected';
      $('path-status').textContent = 'Adjust the filters to inspect a query.';
      $('witness').hidden = true;
      return;
    }
    const r = rows.get(threshold)[selected];
    $('selected-pair').textContent = `${display(r.source)} → ${display(r.target)}`;
    $('path-status').textContent = r.status === 'missing_node' ? `Unresolved: not present in supplied nodes or connections: ${r.missing_ids.join(', ')}` :
      r.status === 'no_path_in_supplied_graph' ? 'No path in the supplied graph at this threshold. This does not establish biological disconnection.' :
      r.hops === 0 ? 'Zero-hop identity path. This is not evidence of a self-connection or feedback circuit.' : `${r.hops} directed hops · one deterministic shortest witness`;
    $('witness').hidden = r.status !== 'reachable' || r.hops === 0;
    $('path-detail').textContent = r.hops ? `Weakest witness edge: ${r.bottleneck} synapses. Ties use lexicographic node IDs, not connection strength.` : '';
    const pages = Math.max(1, Math.ceil(r.edge_counts.length / size));
    hopPage = Math.min(hopPage, pages - 1);
    for (let i = hopPage * size; i < Math.min((hopPage + 1) * size, r.edge_counts.length); i++) {
      const tr = element('tr', null, body);
      cell(tr, i + 1); nodeCell(tr, r.path[i]); nodeCell(tr, r.path[i + 1]);
      cell(tr, r.edge_counts[i]); cell(tr, r.edge_counts[i] - threshold);
    }
    $('hop-label').textContent = `Edges ${r.edge_counts.length ? hopPage * size + 1 : 0}–${Math.min((hopPage + 1) * size, r.edge_counts.length)} of ${r.edge_counts.length}`;
    $('previous-hop').disabled = hopPage === 0; $('next-hop').disabled = hopPage >= pages - 1;
    for (const t of data.thresholds) {
      const other = rows.get(t)[selected], tr = element('tr', null, compare);
      cell(tr, t); cell(tr, statusText[other.status]); cell(tr, dash(other.hops)); cell(tr, dash(other.bottleneck));
    }
  }
  let removalPage = 0, removalSelected = 0, alternativePage = 0, failureKey = '';
  const outcome = {alternative_path: 'Alternative path verified', disconnected: 'Critical — disconnected', unresolved: 'Unresolved'};
  function drawFailures() {
    $('failure-section').hidden = !data.single_edge_failure;
    if (!data.single_edge_failure) return;
    const r = selected < 0 ? null : rows.get(threshold)[selected];
    const key = `${threshold}/${selected}`;
    if (failureKey !== key) { removalPage = 0; removalSelected = 0; alternativePage = 0; failureKey = key; }
    const f = r && r.single_edge_failure;
    const candidates = f ? f.candidates : [];
    $('failure-status').textContent = !f ? 'No query selected.' :
      f.status === 'initially_unreachable' ? 'Initially unreachable: no removal-induced disconnection is claimed.' :
      f.status === 'missing_node' ? 'Missing ID — unresolved baseline.' :
      `${f.status === 'partial' ? 'PARTIAL — unresolved candidates remain' : 'Complete candidate analysis'} · ${f.critical_edges.length} confirmed critical edges · ${f.candidate_count} candidates. ${f.untested_noncritical_edges} other retained edges preserve the baseline witness.`;
    const pages = Math.max(1, Math.ceil(candidates.length / size));
    removalPage = Math.min(removalPage, pages - 1);
    const body = $('removals').tBodies[0]; body.replaceChildren();
    for (let i = removalPage * size; i < Math.min((removalPage + 1) * size, candidates.length); i++) {
      const c = candidates[i], tr = element('tr', null, body);
      nodeCell(tr, c.edge[0]); nodeCell(tr, c.edge[1]); cell(tr, c.synapses); cell(tr, outcome[c.status]);
      const b = element('button', i === removalSelected ? 'Selected' : 'Inspect', cell(tr));
      b.setAttribute('aria-label', `Inspect removal ${c.edge[0]} to ${c.edge[1]}`);
      b.addEventListener('click', () => { removalSelected = i; alternativePage = 0; drawFailures(); $('alternative-heading').focus(); });
    }
    $('removal-page').textContent = `Page ${removalPage + 1} of ${pages}`;
    $('previous-removal').disabled = removalPage === 0; $('next-removal').disabled = removalPage >= pages - 1;
    const c = candidates[removalSelected];
    $('alternative-status').textContent = !c ? (r && r.status === 'reachable' ? 'Zero-hop identity: no candidate removal is needed.' : 'No removal analysis for this baseline.') :
      `Removed ${c.edge[0]} → ${c.edge[1]} (${c.synapses} synapses): ` +
      (c.status === 'disconnected' ? `complete search exhausted, ${c.visited_nodes} nodes reached; target unreachable.` :
       c.status === 'unresolved' ? `unresolved (${c.reason}); no disconnection conclusion.` : `verified alternative, ${c.edge_counts.length} hops.`);
    const edges = c ? c.edge_counts : [], path = c ? c.path : [];
    const altPages = Math.max(1, Math.ceil(edges.length / size));
    alternativePage = Math.min(alternativePage, altPages - 1);
    const alt = $('alternative').tBodies[0]; alt.replaceChildren();
    for (let i = alternativePage * size; i < Math.min((alternativePage + 1) * size, edges.length); i++) {
      const tr = element('tr', null, alt); cell(tr, i + 1); nodeCell(tr, path[i]); nodeCell(tr, path[i + 1]); cell(tr, edges[i]);
    }
    $('alternative-page').textContent = `Page ${alternativePage + 1} of ${altPages} · ${edges.length} edges`;
    $('previous-alternative').disabled = alternativePage === 0; $('next-alternative').disabled = alternativePage >= altPages - 1;
  }
  $('previous-removal').addEventListener('click', () => { removalPage--; drawFailures(); });
  $('next-removal').addEventListener('click', () => { removalPage++; drawFailures(); });
  $('previous-alternative').addEventListener('click', () => { alternativePage--; drawFailures(); });
  $('next-alternative').addEventListener('click', () => { alternativePage++; drawFailures(); });
  function changeThreshold() { threshold = Number($('threshold').value); page = 0; hopPage = 0; drawPairs(); }
  function moveQuery(delta) {
    const pos = filtered.findIndex(f => f.index === selected) + delta;
    if (pos < 0 || pos >= filtered.length) return;
    selected = filtered[pos].index; page = Math.floor(pos / size); hopPage = 0; drawPairs();
  }
  $('kind').textContent = data.provenance.kind.toUpperCase() + ' DATA';
  $('dataset').textContent = data.provenance.dataset; $('revision').textContent = data.provenance.revision;
  $('nodes-count').textContent = data.graph.node_count; $('edges-count').textContent = data.graph.edge_count;
  $('pairs-count').textContent = data.queries.length; $('thresholds-count').textContent = data.thresholds.length;
  for (const t of data.thresholds) { const option = element('option', `≥ ${t}`, $('threshold')); option.value = t; }
  $('threshold').addEventListener('change', changeThreshold);
  for (const id of ['filter', 'status']) $(id).addEventListener(id === 'filter' ? 'input' : 'change', () => { page = 0; hopPage = 0; drawPairs(); });
  $('previous-page').addEventListener('click', () => { page--; drawPairs(); });
  $('next-page').addEventListener('click', () => { page++; drawPairs(); });
  $('previous-query').addEventListener('click', () => moveQuery(-1));
  $('next-query').addEventListener('click', () => moveQuery(1));
  $('previous-hop').addEventListener('click', () => { hopPage--; drawPath(); });
  $('next-hop').addEventListener('click', () => { hopPage++; drawPath(); });
  $('download').addEventListener('click', () => {
    // The embedded text is the exact canonical ASCII report, including newline.
    const raw = $('audit-data').textContent;
    const url = URL.createObjectURL(new Blob([raw], {type: 'application/json'}));
    const a = element('a'); a.href = url; a.download = 'connectome-audit.json'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  for (const key of ['dataset', 'kind', 'revision', 'license', 'attribution', 'selection']) {
    element('dt', key[0].toUpperCase() + key.slice(1), $('provenance'));
    element('dd', data.provenance[key], $('provenance'));
  }
  for (const [role, info] of Object.entries(data.inputs)) {
    const p = element('p', `${role} · ${info.bytes} bytes`, $('hashes'));
    element('br', null, p); element('code', `SHA-256 ${info.sha256}`, p);
  }
  for (const text of [...data.provenance.limitations, ...data.interpretation]) element('li', text, $('limitations'));
  $('technical').textContent = JSON.stringify({schema: data.schema, tool_version: data.tool_version, status: data.status,
    graph: data.graph, semantics: data.semantics, limits: data.limits, work: data.work}, null, 2);
  drawSummary(); drawPairs(); $('load-status').hidden = true;
})();
