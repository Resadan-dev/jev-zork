/*
 * Jev × Zork : lecteur de replay (le DOM). La logique pure vit dans replay-core.js.
 *
 * Tout l'affichage se calcule à partir d'un instant t (renderAt). La même
 * fonction sert à la lecture dans le navigateur et à la vidéo image par image :
 * video/render_video.py ouvre la page en ?capture=1 et pilote window.JevReplay.
 * Les textes du journal viennent d'un fichier : ils passent tous par textContent.
 */
(function () {
  "use strict";

  const Core = window.JevReplayCore;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const params = new URLSearchParams(window.location.search);
  const CAPTURE = params.has("capture");
  const REDUCED_MOTION = !CAPTURE && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const OPTIONS_MAX = 8;
  const OPTIONS_MIN = 3;
  const OPTIONS_DEFAULT = 6;
  const TERMINAL_BLOCKS = 40; // assez pour remplir l'écran ; le haut est rogné en fondu
  const SETTLED = 0.63; // où se poser dans un tour quand on y saute : la décision est prise
  const MAP_CELL = { w: 206, h: 88 };
  const MAP_NODE = { w: 182, h: 52 };
  const MAP_MIN_VIEW = { w: 4.2, h: 3.6 }; // en cases : la carte ne zoome pas trop au début
  const MAP_TRAIL = 12; // la caméra cadre la trace des 12 derniers tours...
  const MAP_REACH = { w: 3, h: 2 }; // ...tant qu'elle tient en 3 × 2 cases : le zoom reste lisible et stable
  const MAP_LABEL_LIMIT = 16;
  const INTENT_LABELS = {
    explore: "Explorer",
    collect: "Ramasser",
    investigate: "Fouiller",
    puzzle: "Résoudre",
    fight: "Combattre",
    escape: "Fuir",
  };
  const END_LABELS = {
    steps: "Fin de partie : limite de coups atteinte",
    victory: "Victoire",
    game_over: "Partie perdue",
    budget: "Partie arrêtée : budget atteint",
    interrupted: "Partie interrompue",
    error: "Partie arrêtée sur une erreur",
  };

  const $ = (id) => document.getElementById(id);
  const dom = {
    turn: $("st-turn"),
    place: $("st-place"),
    score: $("st-score"),
    cost: $("st-cost"),
    model: $("st-model"),
    mockFlag: $("mock-flag"),
    terminal: $("terminal"),
    verdict: $("verdict"),
    confidence: $("confidence-value"),
    gauge: $("gauge-fill"),
    caption: $("options-caption"),
    options: $("options"),
    more: $("options-more"),
    loopNote: $("loop-note"),
    dangerFill: $("danger-fill"),
    dangerValue: $("danger-value"),
    map: $("map"),
    timeline: $("timeline"),
    stream: $("stream"),
    intentLegend: $("intent-legend"),
    introCard: $("intro-card"),
    introMeta: $("intro-meta"),
    introMock: $("intro-mock"),
    outroCard: $("outro-card"),
    outroKicker: $("outro-kicker"),
    outroScore: $("outro-score"),
    outroTurns: $("outro-turns"),
    outroPlaces: $("outro-places"),
    outroFacts: $("outro-facts"),
    outroMock: $("outro-mock"),
    play: $("btn-play"),
    prev: $("btn-prev"),
    next: $("btn-next"),
    scrubber: $("scrubber"),
    clock: $("clock"),
    speed: $("speed"),
    tableButton: $("btn-table"),
    tableView: $("table-view"),
    tableBody: $("table-body"),
    closeTable: $("btn-close-table"),
    fileInput: $("file-input"),
    dropInput: $("file-input-drop"),
    dropError: $("drop-error"),
    tooltip: $("tooltip"),
  };

  // L'état de l'interface : un seul objet, à la frontière avec le DOM.
  const state = {
    journal: null,
    turns: [],
    offset: 0,
    timeline: null,
    layout: null,
    summary: null,
    blocks: [],
    costBefore: [],
    charts: null,
    mapNodes: [],
    mapEdges: [],
    mapHere: null,
    mapViews: new Map(),
    optionRows: [],
    cache: {},
    t: 0,
    playing: false,
    speed: 1,
    clock: null,
    scrubbing: false,
  };

  /* ------------------------------------------------------------ outils */

  function setText(node, text) {
    const value = String(text);
    if (node.textContent !== value) node.textContent = value;
  }

  function svg(tag, attributes, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attributes || {}).forEach(([name, value]) => node.setAttribute(name, String(value)));
    if (parent) parent.appendChild(node);
    return node;
  }

  function html(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function clampInt(value, low, high) {
    return Math.min(high, Math.max(low, Math.round(Number(value) || 0)));
  }

  function shorten(text, limit) {
    return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
  }

  function lerp(from, to, amount) {
    return from + (to - from) * amount;
  }

  function formatClock(seconds) {
    const whole = Math.max(0, Math.floor(seconds));
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
  }

  function formatDate(iso) {
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("fr-FR");
  }

  function isMock() {
    return state.journal.header.judge === "mock";
  }

  function modelName(journal) {
    const answered = journal.turns.find((turn) => turn.model);
    return answered ? answered.model : journal.header.model;
  }

  function intentKeys() {
    return Object.keys(state.journal.header.intents || {}).slice(0, 6);
  }

  /* ------------------------------------------------------------ chargement */

  function load(text, name) {
    const journal = Core.parseJournal(text);
    state.journal = journal;
    state.name = name || "";
    state.layout = Core.layoutMap(journal.turns);
    state.costBefore = journal.turns.reduce(
      (sums, turn, index) => sums.concat(sums[index] + (Number(turn.cost_usd) || 0)),
      [0]
    );
    document.body.dataset.state = "ready";
    const mock = isMock();
    dom.mockFlag.hidden = !mock;
    dom.introMock.hidden = !mock;
    dom.outroMock.hidden = !mock;
    setText(dom.model, mock ? "mock (hasard)" : modelName(journal));
    setText(dom.dropError, "");
    buildMap();
    buildIntentLegend();
    buildTable();
    const duration = setRange(1, journal.turns.length);
    return { turns: journal.turns.length, duration };
  }

  function setRange(from, to, pacing) {
    if (!state.journal) throw new Error("Aucun journal chargé.");
    const all = state.journal.turns;
    const first = clampInt(from, 1, all.length);
    const last = clampInt(to === undefined ? all.length : to, first, all.length);
    state.offset = first - 1;
    state.turns = all.slice(first - 1, last);
    state.timeline = Core.buildTimeline(state.turns, pacing);
    state.summary = Core.summarize(state.journal.header, state.turns);
    state.blocks = Core.transcriptBlocks(state.turns).filter((block) => block.text);
    state.cache = {};
    buildCharts();
    fillCards(first, last);
    dom.scrubber.max = String(state.timeline.total);
    renderAt(0);
    return state.timeline.total;
  }

  /* ------------------------------------------------------------ carte */

  function buildMap() {
    const root = dom.map;
    root.replaceChildren();
    const edgesLayer = svg("g", { class: "map-edges" }, root);
    const nodesLayer = svg("g", { class: "map-nodes" }, root);
    const byId = new Map(state.layout.nodes.map((node) => [node.id, node]));
    const center = (node) => ({ x: node.x * MAP_CELL.w, y: node.y * MAP_CELL.h });
    state.mapEdges = state.layout.edges.map((edge) => {
      const a = center(byId.get(edge.from));
      const b = center(byId.get(edge.to));
      return { edge, line: svg("line", { class: "map-edge", x1: a.x, y1: a.y, x2: b.x, y2: b.y }, edgesLayer) };
    });
    state.mapHere = svg("rect", { class: "map-here", rx: 14, x: 0, y: 0, width: 0, height: 0 }, nodesLayer);
    state.mapNodes = state.layout.nodes.map((node) => {
      const at = center(node);
      const group = svg("g", { class: "map-node", transform: `translate(${at.x} ${at.y})` }, nodesLayer);
      svg("rect", { x: -MAP_NODE.w / 2, y: -MAP_NODE.h / 2, width: MAP_NODE.w, height: MAP_NODE.h, rx: 10 }, group);
      const label = svg("text", { "text-anchor": "middle", "dominant-baseline": "central" }, group);
      label.textContent = shorten(node.name, MAP_LABEL_LIMIT);
      attachNodeHover(group, node);
      return { node, group, center: at };
    });
    state.mapViews = new Map();
  }

  function mapView(index) {
    if (state.mapViews.has(index)) return state.mapViews.get(index);
    const bounds = Core.boundsRecent(state.layout, state.journal.turns, index, MAP_TRAIL, MAP_REACH);
    let minX = (bounds.minX - 0.62) * MAP_CELL.w;
    let maxX = (bounds.maxX + 0.62) * MAP_CELL.w;
    let minY = (bounds.minY - 0.8) * MAP_CELL.h;
    let maxY = (bounds.maxY + 0.8) * MAP_CELL.h;
    const minWidth = MAP_MIN_VIEW.w * MAP_CELL.w;
    const minHeight = MAP_MIN_VIEW.h * MAP_CELL.h;
    if (maxX - minX < minWidth) {
      const middle = (minX + maxX) / 2;
      minX = middle - minWidth / 2;
      maxX = middle + minWidth / 2;
    }
    if (maxY - minY < minHeight) {
      const middle = (minY + maxY) / 2;
      minY = middle - minHeight / 2;
      maxY = middle + minHeight / 2;
    }
    const box = dom.map.getBoundingClientRect();
    const aspect = box.width > 0 && box.height > 0 ? box.width / box.height : 1.3;
    let width = maxX - minX;
    let height = maxY - minY;
    if (width / height < aspect) {
      minX -= (height * aspect - width) / 2;
      width = height * aspect;
    } else {
      minY -= (width / aspect - height) / 2;
      height = width / aspect;
    }
    const view = { x: minX, y: minY, w: width, h: height };
    state.mapViews.set(index, view);
    return view;
  }

  function renderMap(where) {
    const globalIndex = state.offset + where.index;
    const turn = state.journal.turns[globalIndex];
    const appear =
      where.phase === "intro" ? 0 : where.phase === "outro" ? 1 : Core.easeOutCubic(Core.phaseProgress(where.progress, "text"));
    let current = null;
    state.mapNodes.forEach((entry) => {
      const { node, group } = entry;
      const isNew = node.firstTurn === globalIndex;
      const visible = node.firstTurn < globalIndex || (isNew && appear > 0);
      group.style.display = visible ? "" : "none";
      group.style.opacity = isNew ? appear.toFixed(3) : "1";
      group.classList.toggle("is-dark", node.dark);
      const here = visible && node.id === turn.location_id;
      group.classList.toggle("is-current", here);
      if (here) current = entry;
    });
    state.mapEdges.forEach(({ edge, line }) => {
      const isNew = edge.firstTurn === globalIndex;
      line.style.display = edge.firstTurn < globalIndex || (isNew && appear > 0) ? "" : "none";
      line.style.opacity = isNew ? appear.toFixed(3) : "1";
      line.classList.toggle("is-recent", isNew);
    });
    const target = mapView(globalIndex);
    const previous = mapView(Math.max(state.offset, globalIndex - 1));
    const move = where.phase === "turn" ? Core.easeInOutCubic(Core.phaseProgress(where.progress, "text")) : 1;
    const view = [lerp(previous.x, target.x, move), lerp(previous.y, target.y, move), lerp(previous.w, target.w, move), lerp(previous.h, target.h, move)];
    dom.map.setAttribute("viewBox", view.map((value) => value.toFixed(1)).join(" "));
    const ring = state.mapHere;
    if (current && where.phase !== "intro") {
      const pad = 7 + 3 * Math.sin(state.t * 3.2);
      ring.setAttribute("x", (current.center.x - MAP_NODE.w / 2 - pad).toFixed(1));
      ring.setAttribute("y", (current.center.y - MAP_NODE.h / 2 - pad).toFixed(1));
      ring.setAttribute("width", (MAP_NODE.w + 2 * pad).toFixed(1));
      ring.setAttribute("height", (MAP_NODE.h + 2 * pad).toFixed(1));
      ring.style.opacity = (0.35 + 0.25 * Math.cos(state.t * 3.2)).toFixed(3);
    } else {
      ring.setAttribute("width", "0");
    }
  }

  /* ------------------------------------------------------------ graphiques */

  function chartFrame(root, pad) {
    // La taille réelle du panneau : un plancher plus grand ferait rétrécir tout le dessin.
    const box = root.getBoundingClientRect();
    const width = Math.max(120, box.width);
    const height = Math.max(40, box.height);
    root.setAttribute("viewBox", `0 0 ${width} ${height}`);
    root.replaceChildren();
    const count = state.turns.length;
    const left = pad.left;
    const right = width - pad.right;
    const x = (index) => (count <= 1 ? (left + right) / 2 : left + (index / (count - 1)) * (right - left));
    return { width, height, left, right, top: pad.top, bottom: height - pad.bottom, count, x };
  }

  function turnLabels(root, frame) {
    const first = svg("text", { x: frame.x(0), y: frame.height - 4, "text-anchor": "start" }, root);
    first.textContent = `tour ${state.turns[0].turn}`;
    if (frame.count > 1) {
      const last = svg("text", { x: frame.x(frame.count - 1), y: frame.height - 4, "text-anchor": "end" }, root);
      last.textContent = `tour ${state.turns[frame.count - 1].turn}`;
    }
  }

  function revealClip(root, id, frame) {
    const clip = svg("clipPath", { id }, svg("defs", {}, root));
    return svg("rect", { x: 0, y: 0, width: 0, height: frame.height }, clip);
  }

  function buildCharts() {
    state.charts = { timeline: buildTimelineChart(), stream: buildStreamChart() };
  }

  function dangerPath(frame, y) {
    let path = "";
    let drawing = false;
    state.turns.forEach((turn, index) => {
      if (turn.danger === null || turn.danger === undefined) {
        drawing = false;
        return;
      }
      path += `${drawing ? "L" : "M"}${frame.x(index).toFixed(1)} ${y(turn.danger).toFixed(1)} `;
      drawing = true;
    });
    return path.trim();
  }

  function buildTimelineChart() {
    const root = dom.timeline;
    const frame = chartFrame(root, { left: 34, right: 18, top: 22, bottom: 20 });
    const y = (value) => frame.bottom - Core.clamp01(value) * (frame.bottom - frame.top);
    const clipRect = revealClip(root, "reveal-timeline", frame);
    [0, 0.5, 1].forEach((value) => {
      svg("line", { class: value === 0.5 ? "threshold-line" : "grid-line", x1: frame.left, x2: frame.right, y1: y(value), y2: y(value) }, root);
      const tick = svg("text", { x: frame.left - 8, y: y(value), "text-anchor": "end", "dominant-baseline": "central" }, root);
      tick.textContent = Core.formatDecimal(value, value === 0.5 ? 1 : 0);
    });
    const threshold = svg("text", { x: frame.right, y: y(0.5) - 7, "text-anchor": "end" }, root);
    threshold.textContent = "seuil d'hésitation";
    turnLabels(root, frame);
    const revealed = svg("g", { "clip-path": "url(#reveal-timeline)" }, root);
    const points = state.turns.map((turn, index) => [frame.x(index), y(turn.confidence)]);
    const line = points.map(([px, py], index) => `${index ? "L" : "M"}${px.toFixed(1)} ${py.toFixed(1)}`).join(" ");
    const lastX = points[points.length - 1][0].toFixed(1);
    svg("path", { class: "confidence-area", d: `${line} L${lastX} ${y(0)} L${points[0][0].toFixed(1)} ${y(0)} Z` }, revealed);
    svg("path", { class: "danger-line", d: dangerPath(frame, y) }, revealed);
    svg("path", { class: "confidence-line", d: line }, revealed);
    Core.scoreEvents(state.turns).forEach((event) => {
      const cx = frame.x(event.index);
      svg("circle", { class: "points-mark", cx, cy: 9, r: 4.5 }, revealed);
      const label = svg("text", { class: "points-label", x: cx + 8, y: 9, "dominant-baseline": "central" }, revealed);
      label.textContent = `${event.reward > 0 ? "+" : ""}${event.reward}`;
    });
    const cursor = svg("line", { class: "cursor-line", x1: 0, x2: 0, y1: frame.top, y2: frame.bottom }, root);
    const dot = svg("circle", { class: "cursor-dot", r: 5, cx: -20, cy: -20 }, root);
    const hover = svg("rect", { class: "hover-layer", x: frame.left - 10, y: 0, width: frame.right - frame.left + 20, height: frame.height }, root);
    attachChartHover(hover, frame, describeTurn);
    return { frame, clipRect, cursor, dot, y };
  }

  function buildStreamChart() {
    const root = dom.stream;
    const frame = chartFrame(root, { left: 34, right: 18, top: 6, bottom: 20 });
    const keys = intentKeys();
    const layers = Core.streamLayers(Core.intentMatrix(state.turns, keys), 10);
    const middle = (frame.top + frame.bottom) / 2;
    const scale = (frame.bottom - frame.top) * 0.98;
    const y = (value) => middle - value * scale;
    const sampleX = (value) =>
      frame.count <= 1 ? (frame.left + frame.right) / 2 : frame.left + (value / (frame.count - 1)) * (frame.right - frame.left);
    const clipRect = revealClip(root, "reveal-stream", frame);
    turnLabels(root, frame);
    const group = svg("g", { "clip-path": "url(#reveal-stream)" }, root);
    layers.forEach((layer, index) => {
      if (layer.length < 2) return;
      const top = layer.map((point) => `${sampleX(point.x).toFixed(1)} ${y(point.y1).toFixed(1)}`);
      const bottom = layer
        .slice()
        .reverse()
        .map((point) => `${sampleX(point.x).toFixed(1)} ${y(point.y0).toFixed(1)}`);
      const path = svg("path", { class: "stream-layer", d: `M${top.join(" L")} L${bottom.join(" L")} Z` }, group);
      path.style.fill = `var(--intent-${index + 1})`;
    });
    const cursor = svg("line", { class: "cursor-line", x1: 0, x2: 0, y1: frame.top, y2: frame.bottom }, root);
    const hover = svg("rect", { class: "hover-layer", x: frame.left - 10, y: 0, width: frame.right - frame.left + 20, height: frame.height }, root);
    attachChartHover(hover, frame, describeIntent);
    return { frame, clipRect, cursor };
  }

  function revealIndex(where) {
    if (where.phase === "intro") return -1;
    if (where.phase === "outro") return state.turns.length - 1;
    return where.index - 1 + Core.easeOutCubic(Core.phaseProgress(where.progress, "think"));
  }

  function renderCharts(where, turn) {
    const reveal = revealIndex(where);
    const { timeline, stream } = state.charts;
    [timeline, stream].forEach((chart) => {
      const x = chart.frame.x(Math.max(reveal, 0));
      const visible = reveal >= 0;
      chart.clipRect.setAttribute("width", visible ? Math.max(0, x + 10).toFixed(1) : "0");
      chart.cursor.setAttribute("x1", x.toFixed(1));
      chart.cursor.setAttribute("x2", x.toFixed(1));
      chart.cursor.style.display = visible ? "" : "none";
    });
    const settled = where.phase !== "intro" && reveal >= where.index - 1e-6;
    timeline.dot.style.display = settled ? "" : "none";
    timeline.dot.setAttribute("cx", timeline.frame.x(where.index).toFixed(1));
    timeline.dot.setAttribute("cy", timeline.y(turn.confidence).toFixed(1));
  }

  function buildIntentLegend() {
    dom.intentLegend.replaceChildren(
      ...intentKeys().map((key, index) => {
        const item = html("li");
        const swatch = html("span", "key key-intent");
        swatch.style.background = `var(--intent-${index + 1})`;
        swatch.setAttribute("aria-hidden", "true");
        item.append(swatch, document.createTextNode(INTENT_LABELS[key] || key));
        return item;
      })
    );
  }

  /* ------------------------------------------------------------ bulles */

  function tooltipRow(value, label, color) {
    const row = html("p", "tooltip-row");
    if (color) {
      const key = html("span", "tooltip-key");
      key.style.background = color;
      row.appendChild(key);
    }
    row.append(html("strong", "", value), document.createTextNode(label));
    return row;
  }

  function describeTurn(index) {
    const turn = state.turns[index];
    const nodes = [html("p", "tooltip-title", `Tour ${turn.turn} · ${turn.location}`)];
    nodes.push(tooltipRow(Core.formatDecimal(turn.confidence, 2), "confiance", "var(--phosphor)"));
    if (turn.danger !== null && turn.danger !== undefined) {
      nodes.push(tooltipRow(Core.formatPercent(turn.danger), "danger", "var(--danger)"));
    }
    nodes.push(html("p", "tooltip-command", `> ${turn.action}`));
    return nodes;
  }

  function describeIntent(index) {
    const turn = state.turns[index];
    const keys = intentKeys();
    const nodes = [html("p", "tooltip-title", `Tour ${turn.turn} · intentions`)];
    keys
      .map((key, slot) => ({ key, slot, value: Core.clamp01((turn.intent || {})[key]) }))
      .sort((a, b) => b.value - a.value)
      .forEach(({ key, slot, value }) =>
        nodes.push(tooltipRow(Core.formatPercent(value), INTENT_LABELS[key] || key, `var(--intent-${slot + 1})`))
      );
    return nodes;
  }

  function showTooltip(nodes, clientX, clientY) {
    const tip = dom.tooltip;
    tip.replaceChildren(...nodes);
    tip.hidden = false;
    const box = tip.getBoundingClientRect();
    const left = Math.min(window.innerWidth - box.width - 12, clientX + 16);
    const top = Math.max(12, clientY - box.height - 14);
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  }

  function hideTooltip() {
    dom.tooltip.hidden = true;
  }

  function nearestIndex(event, target, frame) {
    const box = target.ownerSVGElement.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * frame.width;
    if (frame.count <= 1) return 0;
    return clampInt(((px - frame.left) / (frame.right - frame.left)) * (frame.count - 1), 0, frame.count - 1);
  }

  function attachChartHover(target, frame, describe) {
    if (CAPTURE) return;
    target.addEventListener("pointermove", (event) => {
      showTooltip(describe(nearestIndex(event, target, frame)), event.clientX, event.clientY);
    });
    target.addEventListener("pointerleave", hideTooltip);
    target.addEventListener("click", (event) => seekTurn(nearestIndex(event, target, frame)));
  }

  function attachNodeHover(group, node) {
    if (CAPTURE) return;
    group.addEventListener("pointermove", (event) => {
      const found = `découvert au tour ${state.journal.turns[node.firstTurn].turn}`;
      const nodes = [html("p", "tooltip-title", node.name), tooltipRow(String(node.visits), node.visits > 1 ? " visites" : " visite")];
      nodes.push(html("p", "tooltip-title", found));
      showTooltip(nodes, event.clientX, event.clientY);
    });
    group.addEventListener("pointerleave", hideTooltip);
  }

  /* ------------------------------------------------------------ rendu d'un instant */

  function renderStatus(where, turn) {
    const intro = where.phase === "intro";
    const all = state.journal.turns;
    setText(dom.turn, intro ? "—" : `${turn.turn} / ${all[all.length - 1].turn}`);
    setText(dom.place, intro ? "—" : turn.dark ? `${turn.location} (dans le noir)` : turn.location);
    const typed = where.phase === "outro" || (where.phase === "turn" && Core.phaseProgress(where.progress, "type") >= 1);
    const score = typed ? turn.score_after ?? turn.score : turn.score;
    setText(dom.score, `${score} / ${state.journal.header.max_score}`);
    // Le coût court depuis le premier tour montré : il rejoint ainsi celui de la carte de fin.
    const globalIndex = state.offset + where.index;
    const spent = state.costBefore[globalIndex] - state.costBefore[state.offset];
    const cost = spent + (intro ? 0 : Number(turn.cost_usd) || 0);
    setText(dom.cost, isMock() ? "—" : Core.formatUsd(cost));
  }

  function visibleBlocks(where) {
    if (where.phase === "intro") return [];
    if (where.phase === "outro") return state.blocks.map((block) => ({ block, chars: block.text.length }));
    const text = REDUCED_MOTION ? 1 : Core.phaseProgress(where.progress, "text");
    const typed = Core.phaseProgress(where.progress, "type");
    const shown = [];
    state.blocks.forEach((block) => {
      if (block.turn < where.index) {
        shown.push({ block, chars: block.text.length });
      } else if (block.turn === where.index) {
        if (block.kind === "text") shown.push({ block, chars: Math.ceil(text * block.text.length) });
        else if (typed > 0) shown.push({ block, chars: Math.ceil(typed * block.text.length) });
      }
    });
    // Le jeu attend la commande : une invite vide, avant que Jev ne tape.
    if (typed === 0 && text >= 1) shown.push({ block: { kind: "command", turn: where.index, text: "" }, chars: 0 });
    return shown;
  }

  function renderTerminal(where) {
    const shown = visibleBlocks(where).slice(-TERMINAL_BLOCKS);
    const waiting = where.phase === "turn" && Core.phaseProgress(where.progress, "type") < 1;
    const blink = waiting && Math.floor(state.t * 2.4) % 2 === 0;
    const signature = `${shown.map((item) => `${item.block.kind}${item.block.turn}:${item.chars}`).join("|")}|${waiting}|${blink}`;
    if (signature === state.cache.terminal) return;
    state.cache.terminal = signature;
    let lastText = -1;
    let lastCommand = -1;
    shown.forEach((item, index) => {
      if (item.block.kind === "text") lastText = index;
      else lastCommand = index;
    });
    const lines = shown.map((item, index) => {
      const line = html("p", `line line-${item.block.kind}`, item.block.text.slice(0, item.chars));
      if (index === lastText || index === lastCommand) line.classList.add("is-current");
      return line;
    });
    if (waiting && lines.length) {
      lines[lines.length - 1].appendChild(html("span", `cursor${blink ? "" : " is-off"}`, " "));
    }
    dom.terminal.replaceChildren(...lines);
  }

  // Combien de lignes d'options tiennent dans le panneau : on mesure une ligne d'essai.
  // Sans cela, la note d'anti-boucle et la barre de danger passeraient sous le panneau voisin.
  function optionCapacity() {
    const list = dom.options;
    // Disposition à une colonne (petits écrans) : pas de hauteur imposée, la liste suit son contenu.
    if (window.getComputedStyle(list).flexGrow === "0") return OPTIONS_DEFAULT;
    const probe = html("li", "option");
    probe.append(
      html("span", "option-marker", "›"),
      html("span", "option-action", "north"),
      html("span", "option-bar"),
      html("span", "option-pct", "0 %"),
      html("span", "option-tries", "")
    );
    list.replaceChildren(probe);
    const rowHeight = probe.getBoundingClientRect().height;
    const gap = parseFloat(window.getComputedStyle(list).rowGap) || 0;
    const room = list.clientHeight;
    list.replaceChildren();
    if (!rowHeight || !room) return OPTIONS_MIN;
    return clampInt(Math.floor((room + gap) / (rowHeight + gap)), OPTIONS_MIN, OPTIONS_MAX);
  }

  function buildOptions(turn) {
    if (state.cache.capacity === undefined) state.cache.capacity = optionCapacity();
    const { options, hidden } = Core.rankOptions(turn, state.cache.capacity);
    state.optionRows = options.map((option) => {
      const row = html("li", "option");
      const marker = html("span", "option-marker", "");
      const action = html("span", "option-action", option.action);
      action.title = option.action;
      const bar = html("span", "option-bar");
      const fill = html("span", "option-fill");
      const strike = html("span", "option-strike");
      bar.append(fill, strike);
      const pct = html("span", "option-pct", "");
      const tries = html("span", "option-tries", option.tries ? `↺ ${option.tries}×` : "");
      if (option.tries) tries.title = `Déjà tenté ${option.tries} fois dans cette situation`;
      row.append(marker, action, bar, pct, tries);
      return { option, row, marker, fill, strike, pct };
    });
    dom.options.replaceChildren(...state.optionRows.map((entry) => entry.row));
    const count = turn.valid_actions.length;
    const plural = count > 1 ? "s" : "";
    setText(dom.caption, `${count} action${plural} valide${plural} proposée${plural} par Jericho`);
    const others = hidden > 1 ? "s" : "";
    setText(dom.more, hidden > 0 ? `+ ${hidden} autre${others} option${others}, moins probable${others}` : "");
  }

  function renderMind(where, turn) {
    const intro = where.phase === "intro";
    const think = intro ? 0 : where.phase === "outro" ? 1 : Core.phaseProgress(where.progress, "think");
    const grow = Core.easeOutCubic(think);
    const loop = intro ? 0 : where.phase === "outro" ? 1 : Core.phaseProgress(where.progress, "loop");
    if (state.cache.mind !== where.index) {
      buildOptions(turn);
      state.cache.mind = where.index;
    }
    if (intro) {
      setText(dom.verdict, "—");
      dom.verdict.dataset.level = "idle";
    } else if (grow < 0.55) {
      setText(dom.verdict, "Jev réfléchit…");
      dom.verdict.dataset.level = "thinking";
    } else {
      const verdict = Core.verdict(turn.confidence);
      setText(dom.verdict, verdict.label);
      dom.verdict.dataset.level = verdict.key;
    }
    setText(dom.confidence, intro ? "—" : Core.formatDecimal(turn.confidence * grow, 2));
    dom.gauge.style.width = `${(Core.clamp01(turn.confidence) * grow * 100).toFixed(2)}%`;
    state.optionRows.forEach(({ option, row, marker, fill, strike, pct }) => {
      fill.style.width = `${(option.probability * grow * 100).toFixed(2)}%`;
      setText(pct, intro ? "" : Core.formatPercent(option.probability * grow));
      const overruled = turn.overridden && option.jevPick;
      row.classList.toggle("is-played", option.played && loop > 0);
      row.classList.toggle("is-overruled", overruled && loop >= 1);
      strike.style.width = overruled ? `${(option.probability * loop * 100).toFixed(2)}%` : "0";
      setText(marker, loop > 0 ? (option.played ? "›" : overruled ? "★" : "") : "");
    });
    if (turn.overridden && loop > 0) {
      const tries = (turn.tries || {})[turn.choice] || 0;
      setText(
        dom.loopNote,
        `↺ Anti-boucle : « ${turn.choice} » déjà tenté ${tries}× ici. Le code joue « ${turn.action} ».`
      );
    } else {
      setText(dom.loopNote, "");
    }
    const danger = turn.danger;
    const known = !intro && danger !== null && danger !== undefined;
    dom.dangerFill.style.width = known ? `${(Core.clamp01(danger) * grow * 100).toFixed(2)}%` : "0";
    setText(dom.dangerValue, known ? Core.formatPercent(danger * grow) : "—");
  }

  function renderCards(where) {
    let intro = 0;
    let outro = 0;
    if (where.phase === "intro") intro = where.progress < 0.8 ? 1 : 1 - (where.progress - 0.8) / 0.2;
    if (where.phase === "outro") outro = Math.min(1, where.progress / 0.18);
    dom.introCard.style.opacity = intro.toFixed(3);
    dom.outroCard.style.opacity = outro.toFixed(3);
    dom.introCard.style.visibility = intro > 0 ? "visible" : "hidden";
    dom.outroCard.style.visibility = outro > 0 ? "visible" : "hidden";
  }

  function renderControls() {
    if (CAPTURE || !state.timeline) return;
    if (!state.scrubbing) dom.scrubber.value = String(state.t);
    setText(dom.clock, `${formatClock(state.t)} / ${formatClock(state.timeline.total)}`);
    setText(dom.play, state.playing ? "❚❚" : "▶");
    dom.play.setAttribute("aria-label", state.playing ? "Pause" : "Lecture");
  }

  function renderAt(t) {
    if (!state.timeline) return;
    state.t = Math.min(Math.max(Number(t) || 0, 0), state.timeline.total);
    const where = Core.locate(state.timeline, state.t);
    const turn = state.turns[where.index];
    renderStatus(where, turn);
    renderTerminal(where);
    renderMind(where, turn);
    renderMap(where);
    renderCharts(where, turn);
    renderCards(where);
    renderControls();
  }

  /* ------------------------------------------------------------ cartons et tableau */

  function fact(parts) {
    const item = html("li");
    parts.forEach((part) => item.append(typeof part === "string" ? document.createTextNode(part) : html("strong", "", part.strong)));
    return item;
  }

  function fillCards(first, last) {
    const header = state.journal.header;
    const summary = state.summary;
    const all = state.journal.turns;
    const whole = first === 1 && last === all.length;
    const model = isMock() ? "mock-random" : modelName(state.journal);
    const span = whole ? `${all.length} coups` : `coups ${state.turns[0].turn} à ${state.turns[state.turns.length - 1].turn} sur ${all.length}`;
    setText(dom.introMeta, [model, span, formatDate(header.started_at)].filter(Boolean).join(" · "));
    const end = state.journal.end;
    const kicker = last === all.length ? (end ? END_LABELS[end.reason] || "Fin de partie" : "Journal incomplet") : "Fin de l'extrait";
    setText(dom.outroKicker, kicker);
    setText(dom.outroScore, `${summary.score} / ${summary.maxScore}`);
    setText(dom.outroTurns, String(summary.turns));
    setText(dom.outroPlaces, String(summary.places));
    const facts = [
      fact(["Jev a hésité ", { strong: `${summary.hesitations} fois` }, ` sur ${summary.turns} (confiance sous 0,5).`]),
      summary.overrides
        ? fact(["L'anti-boucle a corrigé son choix ", { strong: `${summary.overrides} fois` }, "."])
        : fact(["L'anti-boucle n'a jamais eu à corriger son choix."]),
      fact(["Confiance moyenne : ", { strong: Core.formatDecimal(summary.meanConfidence, 2) }, "."]),
    ];
    if (!isMock()) {
      facts.push(
        fact([
          "Coût : ",
          { strong: Core.formatUsd(summary.costUsd) },
          ` pour ${Core.formatInt(summary.inputTokens)} tokens · ${Math.round(summary.latencyMs)} ms par décision.`,
        ])
      );
    }
    dom.outroFacts.replaceChildren(...facts);
  }

  function buildTable() {
    const cell = (text, className) => html("td", className, text);
    dom.tableBody.replaceChildren(
      ...state.journal.turns.map((turn) => {
        const row = html("tr");
        const danger = turn.danger === null || turn.danger === undefined ? "—" : Core.formatPercent(turn.danger);
        row.append(
          cell(String(turn.turn), "num"),
          cell(turn.location),
          cell(turn.action, "mono"),
          cell(turn.overridden ? `${turn.choice} (corrigé)` : turn.choice, "mono"),
          cell(Core.formatDecimal(turn.confidence, 2), "num"),
          cell(danger, "num"),
          cell(String(turn.score_after ?? turn.score), "num")
        );
        return row;
      })
    );
  }

  /* ------------------------------------------------------------ lecture */

  function tick(now) {
    if (!state.playing) return;
    const elapsed = state.clock === null ? 0 : (now - state.clock) / 1000;
    state.clock = now;
    renderAt(state.t + elapsed * state.speed);
    if (state.t >= state.timeline.total) {
      pause();
      return;
    }
    window.requestAnimationFrame(tick);
  }

  function play() {
    if (!state.timeline) return;
    if (state.t >= state.timeline.total) state.t = 0;
    state.playing = true;
    state.clock = null;
    renderControls();
    window.requestAnimationFrame(tick);
  }

  function pause() {
    state.playing = false;
    renderControls();
  }

  function seekTurn(index) {
    const segment = state.timeline.segments[clampInt(index, 0, state.turns.length - 1)];
    renderAt(segment.start + segment.duration * SETTLED);
  }

  function stepTurn(delta) {
    if (!state.timeline) return;
    pause();
    seekTurn(Core.locate(state.timeline, state.t).index + delta);
  }

  // Un fichier refusé ramène à l'écran de dépôt, avec la raison.
  function showLoadError(error) {
    document.body.classList.remove("is-dragging");
    document.body.dataset.state = "empty";
    setText(dom.dropError, error.message);
  }

  function loadFile(file) {
    if (!file) return;
    file
      .text()
      .then((text) => {
        load(text, file.name);
        if (!REDUCED_MOTION) play();
      })
      .catch(showLoadError);
  }

  function wireControls() {
    dom.play.addEventListener("click", () => (state.playing ? pause() : play()));
    dom.prev.addEventListener("click", () => stepTurn(-1));
    dom.next.addEventListener("click", () => stepTurn(1));
    dom.scrubber.addEventListener("input", () => {
      state.scrubbing = true;
      renderAt(Number(dom.scrubber.value));
    });
    dom.scrubber.addEventListener("change", () => {
      state.scrubbing = false;
    });
    dom.speed.addEventListener("change", () => {
      state.speed = Number(dom.speed.value) || 1;
    });
    dom.tableButton.addEventListener("click", () => {
      if (state.journal) dom.tableView.showModal();
    });
    dom.closeTable.addEventListener("click", () => dom.tableView.close());
    [dom.fileInput, dom.dropInput].forEach((input) =>
      input.addEventListener("change", () => loadFile(input.files && input.files[0]))
    );
    document.addEventListener("keydown", (event) => {
      if (!state.timeline || event.target.closest("input, select, textarea, dialog")) return;
      // Un bouton qui a le focus gère lui-même l'espace ; les flèches restent au lecteur.
      if (event.key === " " && event.target.closest("button, label")) return;
      const actions = {
        " ": () => (state.playing ? pause() : play()),
        ArrowLeft: () => stepTurn(-1),
        ArrowRight: () => stepTurn(1),
        Home: () => renderAt(0),
        End: () => renderAt(state.timeline.total),
      };
      if (actions[event.key]) {
        event.preventDefault();
        actions[event.key]();
      }
    });
    window.addEventListener("dragover", (event) => {
      event.preventDefault();
      document.body.classList.add("is-dragging");
    });
    // Chrome donne relatedTarget nul entre deux éléments : on ne retire l'état qu'en sortant de la fenêtre.
    window.addEventListener("dragleave", (event) => {
      const outside =
        event.clientX <= 0 || event.clientY <= 0 || event.clientX >= window.innerWidth || event.clientY >= window.innerHeight;
      if (outside) document.body.classList.remove("is-dragging");
    });
    window.addEventListener("drop", (event) => {
      event.preventDefault();
      document.body.classList.remove("is-dragging");
      loadFile(event.dataTransfer.files && event.dataTransfer.files[0]);
    });
    let resizeTimer = null;
    window.addEventListener("resize", () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        if (!state.journal) return;
        state.mapViews = new Map();
        state.cache = {};
        buildCharts();
        renderAt(state.t);
      }, 150);
    });
  }

  /* ------------------------------------------------------------ démarrage */

  if (CAPTURE) document.body.classList.add("capture");
  wireControls();

  // En lecture directe, les polices web arrivent après le journal : les mesures faites avec la
  // police de secours (options affichables, graphiques, cadre de la carte) sont alors refaites.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => {
      if (!state.journal) return;
      state.mapViews = new Map();
      state.cache = {};
      buildCharts();
      renderAt(state.t);
    });
  }

  const logParam = params.get("log");
  if (logParam) {
    fetch(logParam)
      .then((response) => {
        if (!response.ok) throw new Error(`Impossible de lire ${logParam} (HTTP ${response.status}).`);
        return response.text();
      })
      .then((text) => {
        load(text, logParam);
        if (!CAPTURE && !REDUCED_MOTION) play();
      })
      .catch(showLoadError);
  }

  // Ce que pilote l'enregistreur vidéo (video/render_video.py).
  window.JevReplay = Object.freeze({
    load,
    setRange,
    renderAt(t) {
      renderAt(t);
      return state.t;
    },
    duration: () => (state.timeline ? state.timeline.total : 0),
    // L'instant où la décision du tour est posée ; le numéro est celui du journal.
    turnTime(turn) {
      const segment = state.timeline && state.timeline.segments[turn - 1 - state.offset];
      if (!segment) throw new Error(`Le tour ${turn} n'est pas dans l'extrait.`);
      return segment.start + segment.duration * SETTLED;
    },
    ready: () => document.fonts.ready.then(() => true),
    play,
    pause,
  });
})();
