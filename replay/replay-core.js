/*
 * Jev × Zork : logique pure du lecteur de replay.
 *
 * Aucun accès au DOM ici : ce fichier se teste avec `node --test replay/tests`.
 * Il est chargé dans la page comme un script classique (pas un module ES) pour
 * que replay/index.html s'ouvre d'un double-clic, en file://.
 */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.JevReplayCore = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const FORMAT = 1;
  const HESITANT = 0.5;
  const SURE = 0.8;
  const NNBSP = " ";
  const DEATH = /you have died/i;
  const REQUIRED_TURN_FIELDS = [
    "turn",
    "location",
    "location_id",
    "observation",
    "valid_actions",
    "probabilities",
    "confidence",
    "choice",
    "action",
    "response",
  ];

  /* ------------------------------------------------------------ journal */

  function parseJournal(text) {
    let header = null;
    let end = null;
    const turns = [];
    String(text)
      .split(/\r?\n/)
      .forEach((line, index) => {
        if (!line.trim()) return;
        const where = `Ligne ${index + 1}`;
        let record;
        try {
          record = JSON.parse(line);
        } catch (error) {
          throw new Error(`${where} : JSON invalide.`);
        }
        const type = record && typeof record === "object" ? record.type : undefined;
        if (end) throw new Error(`${where} : enregistrement après la fin de partie.`);
        if (!header) {
          if (type !== "run") {
            throw new Error("Ce fichier ne commence pas par l'en-tête d'une partie de jev-zork.");
          }
          if (record.format !== FORMAT) {
            throw new Error(`Format de journal non pris en charge : ${record.format}.`);
          }
          header = record;
          return;
        }
        if (type === "turn") {
          REQUIRED_TURN_FIELDS.forEach((field) => {
            if (!(field in record)) throw new Error(`${where} : champ « ${field} » manquant.`);
          });
          turns.push(record);
        } else if (type === "end") {
          end = record;
        } else {
          throw new Error(`${where} : type d'enregistrement inattendu (${type}).`);
        }
      });
    if (!header) throw new Error("Journal vide.");
    if (!turns.length) throw new Error("Aucun tour dans ce journal.");
    return { header, turns, end };
  }

  /* ------------------------------------------------------------ nombres */

  function clamp01(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return 0;
    return Math.min(1, Math.max(0, number));
  }

  function easeOutCubic(value) {
    return 1 - Math.pow(1 - clamp01(value), 3);
  }

  function easeInOutCubic(value) {
    const t = clamp01(value);
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  function formatDecimal(value, digits) {
    return Number(value).toFixed(digits).replace(".", ",");
  }

  function formatPercent(value) {
    return `${Math.round(clamp01(value) * 100)}${NNBSP}%`;
  }

  function formatUsd(value) {
    const amount = Number(value) || 0;
    return `${formatDecimal(amount, amount < 1 ? 4 : 2)}${NNBSP}$`;
  }

  function formatInt(value) {
    return String(Math.round(Number(value) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, NNBSP);
  }

  /* ------------------------------------------------------------ rythme */

  // Secondes par tour : un coup sûr passe vite, une hésitation s'attarde.
  const PACING = Object.freeze({
    intro: 3.2,
    outro: 4.8,
    base: 1.9,
    hesitation: 2.4,
    override: 1.2,
    reward: 1.4,
    speed: 1,
  });

  // Découpage d'un tour : le jeu parle, Jev pense, l'anti-boucle corrige, la commande se tape.
  const PHASES = Object.freeze({
    text: [0.0, 0.2],
    think: [0.16, 0.56],
    loop: [0.54, 0.66],
    type: [0.64, 0.86],
  });

  function turnDuration(turn, pacing) {
    const p = { ...PACING, ...pacing };
    const seconds =
      p.base +
      p.hesitation * (1 - clamp01(turn.confidence)) +
      (turn.overridden ? p.override : 0) +
      (turn.reward ? p.reward : 0);
    return seconds / p.speed;
  }

  function buildTimeline(turns, pacing) {
    const p = { ...PACING, ...pacing };
    const intro = p.intro / p.speed;
    let cursor = intro;
    const segments = turns.map((turn, index) => {
      const duration = turnDuration(turn, p);
      const segment = { index, start: cursor, duration };
      cursor += duration;
      return segment;
    });
    return { intro, segments, outroStart: cursor, total: cursor + p.outro / p.speed };
  }

  function locate(timeline, t) {
    const { segments } = timeline;
    if (t < timeline.intro) {
      return { phase: "intro", index: 0, progress: timeline.intro ? clamp01(t / timeline.intro) : 1 };
    }
    if (t >= timeline.outroStart) {
      const span = timeline.total - timeline.outroStart;
      // Sans carton de fin (durée nulle), le dernier instant reste sur le dernier tour.
      if (span <= 0) return { phase: "turn", index: segments.length - 1, progress: 1 };
      return { phase: "outro", index: segments.length - 1, progress: clamp01((t - timeline.outroStart) / span) };
    }
    let low = 0;
    let high = segments.length - 1;
    while (low < high) {
      const middle = (low + high + 1) >> 1;
      if (segments[middle].start <= t) low = middle;
      else high = middle - 1;
    }
    const segment = segments[low];
    return { phase: "turn", index: low, progress: clamp01((t - segment.start) / segment.duration) };
  }

  function phaseProgress(progress, phase) {
    const [start, end] = PHASES[phase];
    return clamp01((progress - start) / (end - start));
  }

  /* ------------------------------------------------------------ décision */

  function verdict(confidence) {
    const value = clamp01(confidence);
    if (value < HESITANT) return { key: "hesitant", label: "Jev hésite" };
    if (value < SURE) return { key: "leaning", label: "Jev penche" };
    return { key: "sure", label: "Jev est sûr de lui" };
  }

  // Les options les plus probables selon Jev ; l'action jouée est toujours montrée.
  function rankOptions(turn, limit) {
    const probabilities = turn.probabilities || {};
    const ranked = Object.keys(probabilities).sort((a, b) => probabilities[b] - probabilities[a]);
    let shown = ranked.slice(0, limit);
    if (limit > 0 && ranked.includes(turn.action) && !shown.includes(turn.action)) {
      shown = shown.slice(0, limit - 1).concat([turn.action]);
    }
    const tries = turn.tries || {};
    const adjusted = turn.adjusted || {};
    return {
      options: shown.map((action) => ({
        action,
        probability: clamp01(probabilities[action]),
        adjusted: action in adjusted ? clamp01(adjusted[action]) : null,
        tries: tries[action] || 0,
        played: action === turn.action,
        jevPick: action === turn.choice,
      })),
      hidden: ranked.length - shown.length,
    };
  }

  /* ------------------------------------------------------------ carte */

  const DIRECTIONS = Object.freeze({
    north: [0, -1],
    south: [0, 1],
    east: [1, 0],
    west: [-1, 0],
    northeast: [1, -1],
    northwest: [-1, -1],
    southeast: [1, 1],
    southwest: [-1, 1],
    up: [0, -1],
    down: [0, 1],
  });
  const SHORT_DIRECTIONS = Object.freeze({
    n: "north",
    s: "south",
    e: "east",
    w: "west",
    ne: "northeast",
    nw: "northwest",
    se: "southeast",
    sw: "southwest",
    u: "up",
    d: "down",
  });
  const MOVE_VERBS = new Set(["go", "walk", "run", "climb"]);

  function directionOf(action) {
    const words = String(action).toLowerCase().trim().split(/\s+/);
    if (words.length === 2 && MOVE_VERBS.has(words[0])) words.shift();
    if (words.length !== 1) return null;
    const word = SHORT_DIRECTIONS[words[0]] || words[0];
    return DIRECTIONS[word] || null;
  }

  function cellKey(cell) {
    return `${cell[0]},${cell[1]}`;
  }

  // La case libre la plus proche de la cible, de préférence dans le sens du mouvement.
  function freeCellNear(target, direction, taken) {
    if (!taken.has(cellKey(target))) return target;
    const score = (cell) => {
      const dx = cell[0] - target[0];
      const dy = cell[1] - target[1];
      const along = direction ? dx * direction[0] + dy * direction[1] : 0;
      return Math.hypot(dx, dy) - 0.25 * along;
    };
    for (let radius = 1; radius <= 16; radius += 1) {
      const ring = [];
      for (let dx = -radius; dx <= radius; dx += 1) {
        for (let dy = -radius; dy <= radius; dy += 1) {
          const cell = [target[0] + dx, target[1] + dy];
          if (Math.max(Math.abs(dx), Math.abs(dy)) === radius && !taken.has(cellKey(cell))) ring.push(cell);
        }
      }
      if (ring.length) return ring.sort((a, b) => score(a) - score(b))[0];
    }
    throw new Error("Carte pleine : plus de case libre autour du lieu.");
  }

  // Place chaque lieu découvert sur une grille, selon la direction prise pour y entrer.
  function layoutMap(turns) {
    const nodes = new Map();
    const taken = new Set();
    const edges = new Map();
    const addNode = (turn, cell, index) => {
      const node = {
        id: turn.location_id,
        name: turn.location,
        x: cell[0],
        y: cell[1],
        firstTurn: index,
        visits: 1,
        dark: Boolean(turn.dark),
      };
      nodes.set(node.id, node);
      taken.add(cellKey(cell));
      return node;
    };
    addNode(turns[0], [0, 0], 0);
    for (let index = 0; index < turns.length - 1; index += 1) {
      const turn = turns[index];
      const next = turns[index + 1];
      const here = nodes.get(turn.location_id);
      if (!turn.dark) {
        here.name = turn.location;
        here.dark = false;
      }
      if (next.location_id === turn.location_id) continue;
      const died = DEATH.test(turn.response || "");
      let there = nodes.get(next.location_id);
      if (there) {
        there.visits += 1;
      } else {
        const direction = died ? null : directionOf(turn.action);
        const step = direction || [1, 1];
        there = addNode(next, freeCellNear([here.x + step[0], here.y + step[1]], direction, taken), index + 1);
      }
      if (died) continue;
      const key = here.id < there.id ? `${here.id}>${there.id}` : `${there.id}>${here.id}`;
      if (!edges.has(key)) {
        edges.set(key, { from: here.id, to: there.id, action: turn.action, firstTurn: index + 1 });
      }
    }
    return { nodes: Array.from(nodes.values()), edges: Array.from(edges.values()) };
  }

  // Le cadre de la caméra : la trace des `span` derniers tours, pas toute la carte. Quand la partie
  // s'étend, la carte entière rendrait les étiquettes illisibles ; la caméra suit donc le joueur.
  // `limit` (en cases, facultatif) borne l'étendue : on remonte la trace tant que tout tient et l'on
  // s'arrête au premier lieu qui ferait dépasser. Le lieu courant est toujours dans le cadre.
  function boundsRecent(layout, turns, index, span, limit) {
    const byId = new Map(layout.nodes.map((node) => [node.id, node]));
    const seen = new Set();
    let box = null;
    for (let i = index; i >= Math.max(0, index - span + 1); i -= 1) {
      const id = turns[i].location_id;
      if (seen.has(id)) continue;
      const node = byId.get(id);
      const next = box
        ? {
            minX: Math.min(box.minX, node.x),
            maxX: Math.max(box.maxX, node.x),
            minY: Math.min(box.minY, node.y),
            maxY: Math.max(box.maxY, node.y),
          }
        : { minX: node.x, maxX: node.x, minY: node.y, maxY: node.y };
      if (box && limit && (next.maxX - next.minX > limit.w || next.maxY - next.minY > limit.h)) break;
      box = next;
      seen.add(id);
    }
    return box;
  }

  /* ------------------------------------------------------------ intentions */

  function intentMatrix(turns, keys) {
    return turns.map((turn) => {
      const intent = turn.intent || {};
      const total = keys.reduce((sum, key) => sum + clamp01(intent[key]), 0);
      return keys.map((key) => (total > 0 ? clamp01(intent[key]) / total : 0));
    });
  }

  // Tangentes de Fritsch-Carlson : la courbe reste monotone entre deux tours, sans dépassement.
  function monotoneTangents(values) {
    const count = values.length;
    const tangents = new Array(count).fill(0);
    if (count < 2) return tangents;
    const slopes = [];
    for (let i = 0; i < count - 1; i += 1) slopes.push(values[i + 1] - values[i]);
    tangents[0] = slopes[0];
    tangents[count - 1] = slopes[count - 2];
    for (let i = 1; i < count - 1; i += 1) {
      tangents[i] = slopes[i - 1] * slopes[i] <= 0 ? 0 : (slopes[i - 1] + slopes[i]) / 2;
    }
    for (let i = 0; i < count - 1; i += 1) {
      if (slopes[i] === 0) {
        tangents[i] = 0;
        tangents[i + 1] = 0;
        continue;
      }
      const a = tangents[i] / slopes[i];
      const b = tangents[i + 1] / slopes[i];
      const length = a * a + b * b;
      if (length > 9) {
        const factor = 3 / Math.sqrt(length);
        tangents[i] = factor * a * slopes[i];
        tangents[i + 1] = factor * b * slopes[i];
      }
    }
    return tangents;
  }

  function sampleMonotone(values, perSegment) {
    const count = values.length;
    if (count === 1) return [{ x: 0, y: values[0] }];
    const tangents = monotoneTangents(values);
    const points = [];
    for (let i = 0; i < count - 1; i += 1) {
      for (let step = 0; step < perSegment; step += 1) {
        const t = step / perSegment;
        const t2 = t * t;
        const t3 = t2 * t;
        const y =
          (2 * t3 - 3 * t2 + 1) * values[i] +
          (t3 - 2 * t2 + t) * tangents[i] +
          (-2 * t3 + 3 * t2) * values[i + 1] +
          (t3 - t2) * tangents[i + 1];
        points.push({ x: i + t, y });
      }
    }
    points.push({ x: count - 1, y: values[count - 1] });
    return points;
  }

  // Aires empilées et centrées : on lisse l'épaisseur de chaque couche, puis on empile.
  function streamLayers(matrix, perSegment) {
    const layerCount = matrix.length ? matrix[0].length : 0;
    const sampled = [];
    for (let k = 0; k < layerCount; k += 1) {
      sampled.push(sampleMonotone(matrix.map((row) => row[k]), perSegment));
    }
    const pointCount = sampled.length ? sampled[0].length : 0;
    const layers = sampled.map(() => []);
    for (let j = 0; j < pointCount; j += 1) {
      const thickness = sampled.map((layer) => Math.max(0, layer[j].y));
      const total = thickness.reduce((sum, value) => sum + value, 0);
      let y = -total / 2;
      for (let k = 0; k < layerCount; k += 1) {
        layers[k].push({ x: sampled[k][j].x, y0: y, y1: y + thickness[k] });
        y += thickness[k];
      }
    }
    return layers;
  }

  /* ------------------------------------------------------------ récit */

  function scoreEvents(turns) {
    return turns.flatMap((turn, index) =>
      turn.reward ? [{ index, reward: turn.reward, action: turn.action }] : []
    );
  }

  // Ce que le terminal affiche : l'écran vu par Jev, sa commande, et la réponse finale du jeu.
  function transcriptBlocks(turns) {
    const blocks = [];
    turns.forEach((turn, index) => {
      blocks.push({ kind: "text", turn: index, text: turn.observation || "" });
      blocks.push({ kind: "command", turn: index, text: turn.action });
    });
    blocks.push({ kind: "text", turn: turns.length, text: turns[turns.length - 1].response || "" });
    return blocks;
  }

  function summarize(header, turns) {
    const count = turns.length;
    const last = turns[count - 1];
    const sum = (pick) => turns.reduce((total, turn) => total + (Number(pick(turn)) || 0), 0);
    const timed = turns.filter((turn) => turn.latency_ms > 0);
    return {
      turns: count,
      score: last.score_after ?? last.score,
      maxScore: header.max_score,
      places: new Set(turns.map((turn) => turn.location_id)).size,
      hesitations: turns.filter((turn) => clamp01(turn.confidence) < HESITANT).length,
      overrides: turns.filter((turn) => turn.overridden).length,
      meanConfidence: sum((turn) => turn.confidence) / count,
      inputTokens: sum((turn) => turn.usage && turn.usage.input_tokens),
      costUsd: sum((turn) => turn.cost_usd),
      latencyMs: timed.length ? timed.reduce((total, turn) => total + turn.latency_ms, 0) / timed.length : 0,
    };
  }

  return Object.freeze({
    FORMAT,
    HESITANT,
    SURE,
    PACING,
    PHASES,
    parseJournal,
    clamp01,
    easeOutCubic,
    easeInOutCubic,
    formatDecimal,
    formatPercent,
    formatUsd,
    formatInt,
    turnDuration,
    buildTimeline,
    locate,
    phaseProgress,
    verdict,
    rankOptions,
    directionOf,
    freeCellNear,
    layoutMap,
    boundsRecent,
    intentMatrix,
    sampleMonotone,
    streamLayers,
    scoreEvents,
    transcriptBlocks,
    summarize,
  });
});
