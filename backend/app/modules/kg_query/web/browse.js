(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const PAGE = 20, MAX_NODES = 150, MAX_EDGES = 250;
  let overview, full = false, loadVersion = 0;
  const nodes = new Map(), edges = new Map();
  let snapshot, graph, selected, searchVersion = 0, detailVersion = 0;
  const make = (tag, text, cls) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (cls) item.className = cls;
    return item;
  };
  const button = (text, action, cls) => {
    const item = make('button', text, cls);
    item.type = 'button';
    item.onclick = action;
    return item;
  };
  const status = message => { $('status').textContent = message; };
  async function request(path, params = {}) {
    const query = new URLSearchParams(params);
    if (snapshot) query.set('snapshot', snapshot);
    const result = await fetch('/modules/kg-explorer/api/browse/' + path + '?' + query);
    if (!result.ok) {
      const body = await result.json().catch(() => ({}));
      throw Error(typeof body.detail === 'string' ? body.detail : 'Không tải được dữ liệu đồ thị.');
    }
    return result.json();
  }
  function properties(parent, raw) {
    let value = raw;
    if (typeof value === 'string') {
      try { value = JSON.parse(value); } catch { /* display stored text */ }
    }
    if (value && Object.keys(value).length) {
      parent.append(make('pre', typeof value === 'string' ? value : JSON.stringify(value, null, 2)));
    } else parent.append(make('p', 'Chưa có thuộc tính bổ sung.'));
  }
  function highlightNode() {
    const ids = [...nodes.keys()];
    [...$('browseGraph').querySelectorAll('.neo-node')].forEach((group, index) => {
      group.classList.toggle('is-selected', ids[index] === selected);
    });
  }
  function render() {
    const edgeList = [...edges.values()];
    graph?.dispose();
    graph = window.createKGOverview($('browseGraph'), [...nodes.values()], edgeList,
      node => showNode(node.id), edge => showEdge(edge));
    $('counts').textContent = `${nodes.size} nút · ${edges.size} cạnh`;
    $('empty').hidden = nodes.size > 0;
    $('legend').replaceChildren();
    for (const type of new Set([...nodes.values()].map(n => n.type))) {
      const entry = make('span'), dot = make('i', '', 'dot');
      dot.style.backgroundColor = graph.colors.get(type);
      entry.append(dot, document.createTextNode(type));
      $('legend').append(entry);
    }
    highlightNode();
  }
  function addNeighborhood(data, includeEdges) {
    if (!nodes.has(data.node.id) && nodes.size >= MAX_NODES) {
      status('Đã đạt giới hạn 150 nút. Đặt lại đồ thị để tiếp tục.');
      return;
    }
    let changed = !nodes.has(data.node.id), capped = false;
    nodes.set(data.node.id, data.node);
    if (includeEdges) for (const row of data.items) {
      if (edges.has(row.edge.id)) continue;
      if (edges.size >= MAX_EDGES || (!nodes.has(row.neighbor.id) && nodes.size >= MAX_NODES)) {
        capped = true;
        continue;
      }
      nodes.set(row.neighbor.id, row.neighbor);
      edges.set(row.edge.id, row.edge);
      changed = true;
    }
    if (changed) render();
    if (capped) status('Đã đạt giới hạn hiển thị (150 nút, 250 cạnh). Đặt lại đồ thị để tải vùng khác.');
  }
  async function showNode(id, offset = 0, expand = false, replace = false) {
    const version = ++detailVersion;
    const detail = $('detail');
    detail.replaceChildren(make('p', 'Đang tải thực thể…'));
    try {
      const data = await request('node', {id, offset, relation: $('relation').value, kind: $('kind').value});
      if (version !== detailVersion) return;
      if (replace) { nodes.clear(); edges.clear(); }
      selected = id;
      status('');
      if (!full) addNeighborhood(data, expand || replace);
      if (!full) graph?.selectNode(id);
      highlightNode();
      detail.replaceChildren(make('span', data.node.type, 'pill'), make('h3', data.node.name), make('small', data.node.id));
      const aliases = make('details'), aliasList = make('div');
      aliases.append(make('summary', `Tên khác (${data.aliases?.length || 0})`), aliasList);
      for (const alias of data.aliases || []) aliasList.append(make('span', alias, 'pill'));
      const attributes = make('details');
      attributes.append(make('summary', 'Thuộc tính'));
      properties(attributes, data.attributes);
      detail.append(aliases, attributes, make('h2', 'Quan hệ lân cận'));
      if (!data.items.length) detail.append(make('p', 'Không có quan hệ phù hợp với bộ lọc.'));
      else if (!full) detail.append(button('Mở rộng lân cận', () => {
        status('');
        addNeighborhood(data, true);
      }, 'primary'));
      for (const {edge, neighbor} of data.items) {
        const arrow = edge.source === id ? '→' : '←';
        detail.append(button(`${arrow} ${edge.type} · ${neighbor.name}`, () => showEdge(edge), 'neighbor'));
      }
      if (offset) detail.append(button('Trang trước', () => showNode(id, offset - PAGE)));
      if (data.more) detail.append(button('Trang sau', () => showNode(id, offset + PAGE)));
    } catch (error) {
      if (version === detailVersion) detail.replaceChildren(make('p', error.message));
    }
  }
  async function showEdge(edge, offset = 0) {
    const version = ++detailVersion, detail = $('detail');
    selected = null;
    highlightNode();
    graph?.highlightEdge([...edges.keys()].indexOf(edge.id));
    detail.replaceChildren(make('p', 'Đang tải quan hệ…'));
    try {
      const data = await request('edge', {id: edge.id, offset});
      if (version !== detailVersion) return;
      detail.replaceChildren(make('span', edge.type, 'pill'), make('h3', 'Quan hệ có hướng'),
        button(data.subject, () => showNode(edge.source), 'neighbor'), make('p', '↓ ' + edge.type),
        button(data.object, () => showNode(edge.target), 'neighbor'), make('small', edge.relation_id || edge.id));
      detail.append(make('h2', `Bằng chứng (${data.evidence_count})`));
      if (data.unavailable) detail.append(make('p', 'Kho bằng chứng hiện chưa khả dụng.'));
      else if (!data.evidence.length) detail.append(make('p', 'Chưa có văn bản bằng chứng cho trang này.'));
      for (const ev of data.evidence) {
        const origin = ev.source_origin || {}, code = origin.source_document_id || ev.document_id;
        const item = make('article', undefined, 'evidence');
        item.append(make('strong', ev.document_title || code || 'Tài liệu nguồn'),
          make('p', [code, ev.section_title || ev.section_id, origin.source_sentence_id || ev.sentence_id].filter(Boolean).join(' · ')),
          make('p', ev.text || 'Chưa có đoạn trích.'));
        detail.append(item);
      }
      const assertions = make('details');
      assertions.append(make('summary', `Phát biểu (${data.assertion_count})`));
      for (const a of data.assertions) {
        assertions.append(make('p', [a.doc_id, a.original_relation_id || a.assertion_id,
          a.confidence == null ? '' : 'Độ tin cậy ' + a.confidence,
          (a.proposition_ids || []).join(', ')].filter(Boolean).join(' · ')));
        properties(assertions, a.properties_json);
      }
      detail.append(assertions);
      if (offset) detail.append(button('Trang trước', () => showEdge(edge, offset - PAGE)));
      if (data.more) detail.append(button('Trang sau', () => showEdge(edge, offset + PAGE)));
    } catch (error) {
      if (version === detailVersion) detail.replaceChildren(make('p', error.message));
    }
  }
  function options(select, values) {
    for (const value of values) {
      const item = make('option', value);
      item.value = value;
      select.append(item);
    }
  }
  async function search(offset = 0, filters = {q: $('term').value.trim(), kind: $('kind').value}) {
    const version = ++searchVersion;
    if (!offset) $('matches').replaceChildren();
    $('moreMatches').hidden = true;
    status('Đang tìm thực thể…');
    try {
      const data = await request('search', {...filters, offset});
      if (version !== searchVersion) return;
      if (!snapshot) {
        snapshot = data.snapshot;
        $('allMode').disabled = false;
        options($('kind'), data.types);
        options($('relation'), data.relations);
        $('snapshot').textContent = snapshot === 'Entity' ? 'Đồ thị Neo4j · chế độ legacy' : 'Snapshot đang phục vụ · ' + snapshot.replace('KGGlobal_', '');
      }
      for (const node of data.items) {
        const item = button(node.name, () => { if (full) setMode(false); showNode(node.id, 0, true, true); }, 'match');
        item.append(make('small', node.type + ' · ' + node.id));
        $('matches').append(item);
      }
      $('moreMatches').hidden = !data.more;
      $('moreMatches').onclick = () => search(offset + PAGE, filters);
      status(data.items.length ? '' : 'Không tìm thấy thực thể phù hợp.');
    } catch (error) {
      if (version === searchVersion) status(error.message);
    }
  }
  async function setMode(all) {
    const version = ++loadVersion;
    ++detailVersion;
    full = all;
    overview?.dispose();
    overview = null;
    if (all) {graph?.dispose();graph = null;}
    $('localMode').setAttribute('aria-pressed', String(!all));
    $('allMode').setAttribute('aria-pressed', String(all));
    $('browseGraph').hidden = all;
    $('overviewGraph').hidden = !all;
    $('empty').hidden = all || nodes.size > 0;
    if (!all) {render();status('');return;}
    $('counts').textContent = 'Đang tải…';
    $('legend').replaceChildren();
    try {
      const graphData = {};
      for (const kind of ['nodes', 'edges']) {
        const items = graphData[kind] = [];
        let offset = 0;
        do {
          const batch = await request('graph', {kind, offset});
          if (version !== loadVersion) return;
          for (const item of batch.items) items.push(item);
          offset = batch.next;
          status(`Đã tải ${items.length.toLocaleString('vi-VN')} ${kind === 'nodes' ? 'nút' : 'cạnh'}…`);
        } while (offset !== null);
      }
      overview = window.createKGOverview($('overviewGraph'), graphData.nodes, graphData.edges,
        node => showNode(node.id), edge => showEdge(edge));
      $('counts').textContent = `${graphData.nodes.length.toLocaleString('vi-VN')} nút · ${graphData.edges.length.toLocaleString('vi-VN')} cạnh`;
      for (const [type,color] of overview.colors) {
        const entry = make('span'), dot = make('i', '', 'dot');
        dot.style.backgroundColor = color;
        entry.append(dot, document.createTextNode(type));
        $('legend').append(entry);
      }
      status(graphData.nodes.length ? 'Đang xem toàn bộ KG đang phục vụ.' : 'Đồ thị hiện chưa có dữ liệu.');
    } catch (error) {
      if (version !== loadVersion) return;
      $('counts').textContent = 'Tải đồ thị thất bại';
      status(error.message);
    }
  }
  $('allMode').disabled = true;
  $('allMode').onclick = () => setMode(true);
  $('localMode').onclick = () => setMode(false);
  const activeGraph = () => full ? overview : graph;
  $('search').onsubmit = event => { event.preventDefault(); search(); };
  $('kind').onchange = () => { search(); if (selected) showNode(selected); };
  $('relation').onchange = () => { if (selected) showNode(selected); };
  $('zoomIn').onclick = () => activeGraph()?.zoom(1.25);
  $('zoomOut').onclick = () => activeGraph()?.zoom(0.8);
  $('fit').onclick = () => activeGraph()?.fit();
  $('fullscreen').onclick = () => window.KGGraph.toggleFullscreen($('graphCard'));
  $('reset').onclick = () => {
    if (full) {overview?.reset();return;}
    detailVersion++;
    selected = null;
    nodes.clear();
    edges.clear();
    render();
    status('');
    $('detail').replaceChildren(make('p', 'Chọn nút hoặc cạnh để xem thông tin.'));
  };
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') $('graphCard').classList.remove('kg-fullscreen');
  });
  new ResizeObserver(() => activeGraph()?.resize($('canvas').clientWidth, $('canvas').clientHeight)).observe($('canvas'));
  search();
})();
