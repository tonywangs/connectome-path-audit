'use strict';
(() => {
  const d = JSON.parse(document.getElementById('graph-data').textContent);
  const $ = id => document.getElementById(id);
  const labels = new Map(d.nodes.map(n => [n.id, n.label]));
  const removed = new Set();
  const adjacency = new Map(d.nodes.map(n => [n.id, []]));
  const compare = (a, b) => {
    const x = Array.from(a, c => c.codePointAt(0)), y = Array.from(b, c => c.codePointAt(0));
    for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i] - y[i];
    return x.length - y.length;
  };
  for (const [a, b, w] of d.edges) adjacency.get(a).push([b, w]);
  for (const edges of adjacency.values()) edges.sort((a, b) => compare(a[0], b[0]));
  let current = null;
  function element(tag, text, className) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (className) e.className = className;
    return e;
  }
  const display = id => `${id} · ${labels.get(id) || 'Unlabelled'}`;
  function option(id) { const e = element('option', display(id)); e.value = id; return e; }
  function path(source, target, threshold, excluded) {
    const parent = new Map([[source, null]]), queue = [source];
    for (let i = 0; i < queue.length && !parent.has(target); i++) {
      const a = queue[i];
      for (const [b, w] of adjacency.get(a)) {
        if (w >= threshold && !excluded.has(b) && !parent.has(b)) {
          parent.set(b, [a, w]); queue.push(b);
        }
      }
    }
    if (!parent.has(target)) return {status: 'unreachable', hops: null, nodes: [], edges: []};
    const nodes = [target], edges = [];
    for (let b = target; parent.get(b) !== null;) {
      const [a, w] = parent.get(b); edges.push({source: a, target: b, synapses: w}); nodes.push(a); b = a;
    }
    nodes.reverse(); edges.reverse();
    return {status: 'reachable', hops: edges.length, nodes, edges};
  }
  const distance = p => p.status === 'unreachable' ? 'No path in supplied graph' : `${p.hops} hop${p.hops === 1 ? '' : 's'}`;
  function svgElement(tag, attrs, text) {
    const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function draw(prefix, result) {
    $(prefix + '-status').textContent = distance(result);
    const container = $(prefix + '-graph'), steps = $(prefix + '-steps');
    container.replaceChildren(); steps.replaceChildren();
    if (!result.nodes.length) { container.append(element('p', 'No directed route at this cutoff with these conditions.', 'empty')); return; }
    const width = result.nodes.length * 250 - 60;
    const svg = svgElement('svg', {width, height: 115, viewBox: `0 0 ${width} 115`, role: 'img', 'aria-label': result.nodes.map(display).join(' → ')});
    result.nodes.forEach((id, i) => {
      const x = i * 250;
      if (i) {
        svg.append(svgElement('line', {x1: x - 65, y1: 57, x2: x - 12, y2: 57}));
        svg.append(svgElement('polygon', {points: `${x - 3},57 ${x - 13},52 ${x - 13},62`}));
        svg.append(svgElement('text', {x: x - 37, y: 43, 'text-anchor': 'middle'}, result.edges[i - 1].synapses));
      }
      const g = svgElement('g', {});
      g.append(svgElement('title', {}, display(id)));
      g.append(svgElement('rect', {x: x + 1, y: 20, width: 184, height: 74, rx: 8}));
      g.append(svgElement('text', {x: x + 13, y: 46, class: 'node-title'}, id));
      const label = labels.get(id) || 'Unlabelled';
      g.append(svgElement('text', {x: x + 13, y: 69, class: 'node-label'}, label.length > 24 ? label.slice(0, 23) + '…' : label));
      svg.append(g);
      const li = element('li', display(id));
      if (i > 0) li.prepend(document.createTextNode(`← ${result.edges[i - 1].synapses} synapses · `));
      if (i > 0 && i < result.nodes.length - 1 && !removed.has(id)) {
        const button = element('button', 'Remove'); button.dataset.remove = id;
        button.setAttribute('aria-label', `Remove intermediate neuron ${id}`);
        button.addEventListener('click', () => { removed.add(id); update(); }); li.append(button);
      }
      if (removed.has(id)) li.append(element('strong', ' · removed in experiment'));
      steps.append(li);
    });
    container.append(svg);
  }
  function update() {
    const threshold = Number($('threshold').value), source = $('source').value, target = $('target').value;
    if (!Number.isSafeInteger(threshold) || threshold < 1 || !$('threshold').value.trim()) {
      $('input-error').textContent = 'Enter a positive whole synapse count, at most 9007199254740991.';
      current = null; $('download').disabled = true;
      $('experiment-status').textContent = 'Invalid cutoff. No current experiment results.';
      for (const prefix of ['baseline', 'after']) {
        $(prefix + '-status').textContent = 'Not computed'; $(prefix + '-graph').replaceChildren(); $(prefix + '-steps').replaceChildren();
      }
      $('comparison').replaceChildren(); return;
    }
    $('input-error').textContent = ''; $('download').disabled = false;
    removed.delete(source); removed.delete(target);
    const priorRemovalChoice = $('remove-node').value;
    const placeholder = element('option', 'Choose a neuron…'); placeholder.value = '';
    $('remove-node').replaceChildren(placeholder);
    for (const n of d.nodes) if (n.id !== source && n.id !== target && !removed.has(n.id)) $('remove-node').append(option(n.id));
    if ([...$('remove-node').options].some(o => o.value === priorRemovalChoice)) $('remove-node').value = priorRemovalChoice;
    $('remove-button').disabled = !$('remove-node').value;
    $('reset').disabled = !removed.size;
    $('removed').replaceChildren();
    for (const id of [...removed].sort(compare)) {
      const button = element('button', `Restore ${display(id)} ×`); button.dataset.restore = id;
      button.addEventListener('click', () => { removed.delete(id); update(); }); $('removed').append(button);
    }
    if (!removed.size) $('removed').append(element('span', 'No neurons removed.', 'hint'));
    const baseline = path(source, target, threshold, new Set()), after = path(source, target, threshold, removed);
    const cutoffs = [...new Set([1, 3, 5, 10, 20, threshold])].sort((a, b) => a - b);
    const comparisons = cutoffs.map(cutoff => ({threshold: cutoff, baseline: path(source, target, cutoff, new Set()), after: path(source, target, cutoff, removed)}));
    current = {schema: 'connectome-experiment/v1', source, target, threshold,
      removed: [...removed].sort(compare), baseline, after, comparisons,
      inputs: d.inputs, provenance: d.provenance, semantics: d.semantics};
    $('experiment-status').textContent = `${source} → ${target} · cutoff ≥ ${threshold} · ${removed.size} neuron${removed.size === 1 ? '' : 's'} removed simultaneously`;
    draw('baseline', baseline); draw('after', after);
    $('comparison').replaceChildren();
    for (const row of comparisons) {
      const tr = element('tr'); if (row.threshold === threshold) tr.className = 'selected';
      for (const text of [row.threshold, distance(row.baseline), distance(row.after)]) tr.append(element('td', text));
      const td = element('td'), button = element('button', 'Use cutoff'); button.setAttribute('aria-label', `Use cutoff ${row.threshold}`);
      button.addEventListener('click', () => { $('threshold').value = row.threshold; update(); }); td.append(button); tr.append(td); $('comparison').append(tr);
    }
  }
  for (const id of ['source', 'target']) {
    for (const n of d.nodes) $(id).append(option(n.id));
    $(id).value = d.initial[id]; $(id).addEventListener('change', update);
  }
  $('threshold').value = d.initial.threshold;
  $('threshold').addEventListener('input', update);
  $('swap').addEventListener('click', () => { const s = $('source').value; $('source').value = $('target').value; $('target').value = s; update(); });
  $('remove-node').addEventListener('change', () => { $('remove-button').disabled = !$('remove-node').value; });
  $('remove-button').addEventListener('click', () => {
    const id = $('remove-node').value;
    if (id && id !== $('source').value && id !== $('target').value) { removed.add(id); update(); }
  });
  $('reset').addEventListener('click', () => { removed.clear(); update(); });
  $('download').addEventListener('click', () => {
    if (!current) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(current, null, 2) + '\n'], {type: 'application/json'}));
    const a = element('a'); a.href = url; a.download = 'connectome-experiment.json'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $('dataset').textContent = `${d.provenance.kind.toUpperCase()} DATA · ${d.provenance.dataset}`;
  for (const text of [`${d.nodes.length.toLocaleString('en')} neurons`, `${d.edges.length.toLocaleString('en')} directed edges`, `${d.edges.reduce((s, e) => s + e[2], 0).toLocaleString('en')} synapses`]) $('stats').append(element('span', text));
  for (const key of ['revision', 'license', 'attribution', 'selection']) $('provenance').append(element('dt', key.toUpperCase()), element('dd', d.provenance[key]));
  $('hashes').textContent = JSON.stringify(d.inputs, null, 2);
  for (const text of d.provenance.limitations) $('limits').append(element('li', text));
  update(); $('load-status').hidden = true;
})();
