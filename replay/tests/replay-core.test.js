// Tests de la logique du replay : node --test replay/tests
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const Core = require("../replay-core.js");

const HEADER = {
  type: "run",
  format: 1,
  judge: "jev",
  model: "jev-latest",
  max_score: 350,
  intents: { explore: "Go somewhere new", collect: "Pick up" },
};

function turn(overrides) {
  return {
    type: "turn",
    turn: 1,
    location: "West of House",
    location_id: 180,
    dark: false,
    observation: "West of House",
    valid_actions: ["open mailbox", "north"],
    probabilities: { "open mailbox": 0.61, north: 0.39 },
    confidence: 0.42,
    choice: "open mailbox",
    action: "open mailbox",
    overridden: false,
    tries: {},
    adjusted: { "open mailbox": 0.61, north: 0.39 },
    danger: 0.03,
    intent: { explore: 0.25, collect: 0.75 },
    response: "Opening the small mailbox reveals a leaflet.",
    reward: 0,
    score: 0,
    score_after: 0,
    latency_ms: 200,
    usage: { input_tokens: 600, output_tokens: 40 },
    cost_usd: 0.0000252,
    ...overrides,
  };
}

function journal(records) {
  return records.map((record) => JSON.stringify(record)).join("\n");
}

test("parseJournal lit l'en-tête, les tours et la fin", () => {
  const parsed = Core.parseJournal(journal([HEADER, turn(), turn({ turn: 2 }), { type: "end", reason: "steps" }]));
  assert.equal(parsed.header.model, "jev-latest");
  assert.equal(parsed.turns.length, 2);
  assert.equal(parsed.end.reason, "steps");
});

test("parseJournal accepte un journal sans fin (partie interrompue)", () => {
  const parsed = Core.parseJournal(journal([HEADER, turn()]) + "\n\n");
  assert.equal(parsed.end, null);
});

test("parseJournal refuse les journaux cassés avec un message utile", () => {
  assert.throws(() => Core.parseJournal(journal([turn()])), /en-tête/);
  assert.throws(() => Core.parseJournal(journal([HEADER]) + "\n{oops"), /Ligne 2 : JSON invalide/);
  assert.throws(() => Core.parseJournal(journal([{ ...HEADER, format: 9 }, turn()])), /Format/);
  const incomplete = turn();
  delete incomplete.action;
  assert.throws(() => Core.parseJournal(journal([HEADER, incomplete])), /« action » manquant/);
  assert.throws(() => Core.parseJournal(journal([HEADER, { type: "end" }, turn()])), /après la fin/);
  assert.throws(() => Core.parseJournal(journal([HEADER, { type: "chat" }])), /inattendu/);
  assert.throws(() => Core.parseJournal(journal([HEADER])), /Aucun tour/);
  assert.throws(() => Core.parseJournal(""), /vide/);
});

test("une hésitation dure plus longtemps qu'un coup sûr", () => {
  const sure = Core.turnDuration(turn({ confidence: 1 }));
  const unsure = Core.turnDuration(turn({ confidence: 0 }));
  assert.equal(sure, Core.PACING.base);
  assert.equal(unsure, Core.PACING.base + Core.PACING.hesitation);
  assert.ok(Core.turnDuration(turn({ confidence: 1, overridden: true, reward: 5 })) > sure);
  assert.equal(Core.turnDuration(turn({ confidence: 1 }), { speed: 2 }), sure / 2);
});

test("buildTimeline et locate situent chaque instant", () => {
  const turns = [turn({ confidence: 1 }), turn({ confidence: 1 }), turn({ confidence: 1 })];
  const timeline = Core.buildTimeline(turns);
  const { intro, base, outro } = Core.PACING;
  assert.equal(timeline.segments[1].start, intro + base);
  assert.equal(timeline.total, intro + 3 * base + outro);
  assert.deepEqual(Core.locate(timeline, 0), { phase: "intro", index: 0, progress: 0 });
  assert.deepEqual(Core.locate(timeline, intro), { phase: "turn", index: 0, progress: 0 });
  const middle = Core.locate(timeline, intro + base * 1.5);
  assert.equal(middle.index, 1);
  assert.ok(Math.abs(middle.progress - 0.5) < 1e-9);
  assert.equal(Core.locate(timeline, timeline.total + 1).phase, "outro");
  assert.equal(Core.locate(timeline, timeline.total + 1).progress, 1);
});

test("sans cartons, la partie commence et finit sur un tour (GIF qui boucle)", () => {
  const turns = [turn({ confidence: 1 }), turn({ confidence: 1 })];
  const timeline = Core.buildTimeline(turns, { intro: 0, outro: 0 });
  assert.equal(timeline.total, 2 * Core.PACING.base);
  assert.deepEqual(Core.locate(timeline, 0), { phase: "turn", index: 0, progress: 0 });
  assert.deepEqual(Core.locate(timeline, timeline.total), { phase: "turn", index: 1, progress: 1 });
  assert.deepEqual(Core.locate(timeline, timeline.total + 5), { phase: "turn", index: 1, progress: 1 });
});

test("phaseProgress découpe un tour en étapes", () => {
  assert.equal(Core.phaseProgress(0, "text"), 0);
  assert.equal(Core.phaseProgress(0.2, "text"), 1);
  assert.ok(Math.abs(Core.phaseProgress(0.36, "think") - 0.5) < 1e-9);
  assert.equal(Core.phaseProgress(1, "type"), 1);
});

test("verdict suit les seuils de confiance", () => {
  assert.equal(Core.verdict(0.42).label, "Jev hésite");
  assert.equal(Core.verdict(0.6).key, "leaning");
  assert.equal(Core.verdict(0.95).label, "Jev est sûr de lui");
});

test("rankOptions trie, limite et montre toujours l'action jouée", () => {
  const record = turn({
    probabilities: { a: 0.5, b: 0.3, c: 0.15, d: 0.05 },
    choice: "a",
    action: "d",
    overridden: true,
    tries: { a: 2 },
  });
  const { options, hidden } = Core.rankOptions(record, 2);
  assert.deepEqual(
    options.map((option) => option.action),
    ["a", "d"]
  );
  assert.equal(hidden, 2);
  assert.equal(options[0].jevPick, true);
  assert.equal(options[0].tries, 2);
  assert.equal(options[1].played, true);
});

test("directionOf reconnaît les déplacements", () => {
  assert.deepEqual(Core.directionOf("north"), [0, -1]);
  assert.deepEqual(Core.directionOf("go east"), [1, 0]);
  assert.deepEqual(Core.directionOf("ne"), [1, -1]);
  assert.deepEqual(Core.directionOf("climb down"), [0, 1]);
  assert.equal(Core.directionOf("open mailbox"), null);
  assert.equal(Core.directionOf("climb tree"), null);
});

test("layoutMap place les lieux selon la direction prise", () => {
  const turns = [
    turn({ location_id: 180, location: "West of House", action: "north" }),
    turn({ location_id: 81, location: "North of House", action: "east" }),
    turn({ location_id: 79, location: "Behind House", action: "west" }),
    turn({ location_id: 81, location: "North of House", action: "look" }),
  ];
  const layout = Core.layoutMap(turns);
  const at = Object.fromEntries(layout.nodes.map((node) => [node.name, [node.x, node.y]]));
  assert.deepEqual(at["West of House"], [0, 0]);
  assert.deepEqual(at["North of House"], [0, -1]);
  assert.deepEqual(at["Behind House"], [1, -1]);
  assert.equal(layout.nodes.find((node) => node.id === 81).visits, 2);
  assert.equal(layout.edges.length, 2);
  // La caméra cadre les derniers lieux visités, pas toute la carte.
  assert.deepEqual(Core.boundsRecent(layout, turns, 1, 2), { minX: 0, maxX: 0, minY: -1, maxY: 0 });
  assert.deepEqual(Core.boundsRecent(layout, turns, 2, 2), { minX: 0, maxX: 1, minY: -1, maxY: -1 });
  assert.deepEqual(Core.boundsRecent(layout, turns, 2, 50), { minX: 0, maxX: 1, minY: -1, maxY: 0 });
  // Une limite d'étendue coupe la trace au premier lieu qui ferait dépasser ; le lieu courant reste.
  assert.deepEqual(Core.boundsRecent(layout, turns, 2, 50, { w: 0, h: 5 }), { minX: 1, maxX: 1, minY: -1, maxY: -1 });
  assert.deepEqual(Core.boundsRecent(layout, turns, 2, 50, { w: 5, h: 0 }), { minX: 0, maxX: 1, minY: -1, maxY: -1 });
});

test("layoutMap évite les cases occupées et ne relie pas une mort", () => {
  const turns = [
    turn({ location_id: 1, location: "A", action: "north" }),
    turn({ location_id: 2, location: "B", action: "east" }),
    turn({ location_id: 3, location: "C", action: "southwest" }),
    turn({ location_id: 4, location: "D", action: "south", response: "****  You have died  ****" }),
    turn({ location_id: 5, location: "Forest", action: "look" }),
  ];
  const layout = Core.layoutMap(turns);
  const cells = layout.nodes.map((node) => `${node.x},${node.y}`);
  assert.equal(new Set(cells).size, cells.length);
  assert.ok(!layout.edges.some((edge) => edge.to === 5 || edge.from === 5));
});

test("freeCellNear préfère la direction du mouvement", () => {
  const taken = new Set(["0,-1"]);
  assert.deepEqual(Core.freeCellNear([0, -1], [0, -1], taken), [0, -2]);
});

test("intentMatrix normalise chaque tour et met des zéros quand l'intention manque", () => {
  const matrix = Core.intentMatrix([turn(), turn({ intent: {} })], ["explore", "collect"]);
  assert.deepEqual(matrix, [
    [0.25, 0.75],
    [0, 0],
  ]);
});

test("sampleMonotone passe par les tours sans dépasser", () => {
  const points = Core.sampleMonotone([0, 0, 1, 1], 8);
  assert.equal(points.length, 3 * 8 + 1);
  assert.deepEqual(points[16], { x: 2, y: 1 });
  assert.ok(points.every((point) => point.y >= -1e-12 && point.y <= 1 + 1e-12));
});

test("streamLayers empile des couches contiguës, centrées sur zéro", () => {
  const layers = Core.streamLayers(
    [
      [0.2, 0.8],
      [0.6, 0.4],
    ],
    4
  );
  assert.equal(layers.length, 2);
  layers[0].forEach((point, j) => {
    assert.ok(Math.abs(point.y1 - layers[1][j].y0) < 1e-12);
    assert.ok(Math.abs(point.y0 + layers[1][j].y1) < 1e-12);
  });
});

test("le récit alterne écrans et commandes, puis la dernière réponse", () => {
  const blocks = Core.transcriptBlocks([turn(), turn({ observation: "Leaflet.", action: "take leaflet", response: "Taken." })]);
  assert.deepEqual(
    blocks.map((block) => block.kind),
    ["text", "command", "text", "command", "text"]
  );
  assert.equal(blocks[4].text, "Taken.");
});

test("summarize compte les hésitations, les corrections et le coût", () => {
  const turns = [
    turn({ confidence: 0.3, overridden: true }),
    turn({ confidence: 0.9, location_id: 81, reward: 5, score_after: 5 }),
  ];
  const summary = Core.summarize(HEADER, turns);
  assert.equal(summary.turns, 2);
  assert.equal(summary.hesitations, 1);
  assert.equal(summary.overrides, 1);
  assert.equal(summary.places, 2);
  assert.equal(summary.score, 5);
  assert.equal(summary.inputTokens, 1200);
  assert.ok(Math.abs(summary.costUsd - 0.0000504) < 1e-12);
  assert.equal(Core.scoreEvents(turns).length, 1);
});

test("les nombres s'écrivent à la française", () => {
  assert.equal(Core.formatDecimal(0.42, 2), "0,42");
  assert.equal(Core.formatPercent(0.614), "61 %");
  assert.equal(Core.formatUsd(0.01234), "0,0123 $");
  assert.equal(Core.formatInt(294000), "294 000");
});
