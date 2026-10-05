export function recencyWeight(isoTime, nowMs = Date.now()) {
  const t = Date.parse(isoTime);
  if (!Number.isFinite(t)) return 0.1;
  const age = Math.max(0, nowMs - t);
  const HOUR = 60 * 60 * 1000;
  const DAY = 24 * HOUR;
  if (age < 6 * HOUR) return 1.0;
  if (age < 24 * HOUR) return 0.8;
  if (age < 3 * DAY) return 0.5;
  if (age <= 7 * DAY) return 0.25;
  return 0.1;
}

function statKey(group, value) {
  return `${group}:${String(value ?? "")}`;
}

function cloneState(state) {
  return {
    events: Array.isArray(state?.events) ? [...state.events] : [],
    stats: state?.stats && typeof state.stats === "object" ? { ...state.stats } : {},
  };
}

export function recordFeedback(state, candidate, kind, atIso = new Date().toISOString()) {
  const next = cloneState(state);
  const event = {
    at: atIso,
    kind,
    id: candidate.id ?? "",
    server: candidate.server ?? "",
    port: String(candidate.port ?? ""),
    source: candidate.source ?? "",
    domain: candidate.domain ?? "",
    secret: candidate.secret ?? "",
    proxyKind: candidate.kind ?? "",
  };
  next.events.unshift(event);
  next.events = next.events.slice(0, 500);

  const features = [
    ["id", event.id],
    ["source", event.source],
    ["port", event.port],
    ["kind", event.proxyKind],
    ["domain", event.domain],
    ["secret", event.secret],
  ];
  for (const [group, value] of features) {
    if (!value) continue;
    const key = statKey(group, value);
    const prev = next.stats[key] ?? { good: 0, bad: 0, lastGoodAt: null, lastBadAt: null };
    const updated = { ...prev };
    if (kind === "good") {
      updated.good = (updated.good ?? 0) + 1;
      updated.lastGoodAt = atIso;
    } else if (kind === "bad") {
      updated.bad = (updated.bad ?? 0) + 1;
      updated.lastBadAt = atIso;
    }
    next.stats[key] = updated;
  }
  return next;
}

export function featureScore(stats, weight = 1, nowMs = Date.now()) {
  if (!stats) return 0;
  const good = stats.good ?? 0;
  const bad = stats.bad ?? 0;
  const goodRecency = stats.lastGoodAt ? recencyWeight(stats.lastGoodAt, nowMs) : 0;
  const badRecency = stats.lastBadAt ? recencyWeight(stats.lastBadAt, nowMs) : 0;
  return weight * (good * 4 * goodRecency - bad * 1.25 * badRecency);
}

export function candidateScore(candidate, feedbackState, nowMs = Date.now()) {
  const stats = feedbackState?.stats ?? {};
  const exact = featureScore(stats[statKey("id", candidate.id)], 12, nowMs);
  const secret = featureScore(stats[statKey("secret", candidate.secret)], 8, nowMs);
  const domain = featureScore(stats[statKey("domain", candidate.domain)], 5, nowMs);
  const source = featureScore(stats[statKey("source", candidate.source)], 4, nowMs);
  const port = featureScore(stats[statKey("port", String(candidate.port ?? ""))], 3, nowMs);
  const kind = featureScore(stats[statKey("kind", candidate.kind)], 2, nowMs);
  return exact + secret + domain + source + port + kind;
}

export function loadFeedback(storage) {
  try {
    const raw = storage.getItem("proxy-feedback-state");
    if (!raw) return { events: [], stats: {} };
    const parsed = JSON.parse(raw);
    return cloneState(parsed);
  } catch {
    return { events: [], stats: {} };
  }
}

export function saveFeedback(storage, state) {
  storage.setItem("proxy-feedback-state", JSON.stringify(cloneState(state)));
}


function latestKindForId(state, id) {
  const event = (state?.events ?? []).find(e => e.id === id);
  return event?.kind ?? null;
}

export function selectBatch(candidates, feedbackState, size = 10, nowMs = Date.now()) {
  const eligible = candidates.filter(c => latestKindForId(feedbackState, c.id) !== "bad");
  const scored = eligible.map((candidate, index) => ({
    candidate,
    index,
    score: candidateScore(candidate, feedbackState, nowMs),
  }));

  const exploit = scored
    .filter(x => x.score > 0)
    .sort((a, b) => b.score - a.score || a.index - b.index);

  const explore = scored
    .filter(x => x.score <= 0)
    .sort((a, b) => a.index - b.index);

  const exploreSlots = size >= 5 && explore.length >= 2 ? Math.min(2, size) : Math.min(explore.length, size);
  const exploitSlots = Math.max(0, size - exploreSlots);

  const picked = [...exploit.slice(0, exploitSlots), ...explore.slice(0, exploreSlots)];
  if (picked.length < size) {
    const used = new Set(picked.map(x => x.candidate.id));
    const remainder = [...exploit.slice(exploitSlots), ...explore.slice(exploreSlots)]
      .filter(x => !used.has(x.candidate.id));
    picked.push(...remainder.slice(0, size - picked.length));
  }

  return picked
    .sort((a, b) => {
      const aExplore = a.score <= 0;
      const bExplore = b.score <= 0;
      if (aExplore !== bExplore) return aExplore ? 1 : -1;
      return b.score - a.score || a.index - b.index;
    })
    .map(x => x.candidate);
}


export function rejectBatch(state, candidates, ids, atIso = new Date().toISOString()) {
  let next = cloneState(state);
  const byId = new Map(candidates.map(c => [c.id, c]));
  for (const id of ids) {
    const latest = (next.events ?? []).find(e => e.id === id);
    if (latest?.kind === "good") continue;
    const candidate = byId.get(id);
    if (!candidate) continue;
    if (latest?.kind !== "bad") {
      next = recordFeedback(next, candidate, "bad", atIso);
    }
  }
  return next;
}

function ageBandFor(isoTime, nowMs = Date.now()) {
  const age = Math.max(0, nowMs - Date.parse(isoTime));
  const DAY = 24 * 60 * 60 * 1000;
  if (age < DAY) return "today";
  if (age < 2 * DAY) return "yesterday";
  if (age <= 7 * DAY) return "recent";
  return "stale";
}

export function workingReserve(feedbackState, candidateCatalog = {}, nowMs = Date.now()) {
  const events = feedbackState?.events ?? [];
  const latestById = new Map();
  for (const event of events) {
    if (!latestById.has(event.id)) latestById.set(event.id, event);
  }

  const goodEventsById = new Map();
  for (const event of events) {
    if (event.kind !== "good") continue;
    if (!goodEventsById.has(event.id)) goodEventsById.set(event.id, []);
    goodEventsById.get(event.id).push(event);
  }

  const out = [];
  for (const [id, goodEvents] of goodEventsById.entries()) {
    if (latestById.get(id)?.kind !== "good") continue;
    const latestGood = goodEvents.reduce((best, e) => Date.parse(e.at) > Date.parse(best.at) ? e : best);
    const catalog = candidateCatalog[id] ?? {};
    out.push({
      id,
      server: catalog.server ?? latestGood.server ?? "",
      port: String(catalog.port ?? latestGood.port ?? ""),
      source: catalog.source ?? latestGood.source ?? "",
      secret: catalog.secret ?? latestGood.secret ?? "",
      lastGoodAt: latestGood.at,
      goodCount: goodEvents.length,
      ageBand: ageBandFor(latestGood.at, nowMs),
    });
  }

  out.sort((a, b) =>
    Date.parse(b.lastGoodAt) - Date.parse(a.lastGoodAt) ||
    b.goodCount - a.goodCount ||
    a.id.localeCompare(b.id)
  );
  return out;
}


export function poolStatus(candidates, feedbackState, generatedAt, nowMs = Date.now()) {
  const latestById = new Map();
  for (const event of feedbackState?.events ?? []) {
    if (!latestById.has(event.id)) latestById.set(event.id, event.kind);
  }
  let rejected = 0;
  let eligible = 0;
  for (const candidate of candidates) {
    if (latestById.get(candidate.id) === "bad") rejected += 1;
    else eligible += 1;
  }
  const generatedMs = Date.parse(generatedAt);
  const nextRefreshAt = new Date((Number.isFinite(generatedMs) ? generatedMs : nowMs) + 2 * 60 * 60 * 1000).toISOString();
  return {
    eligible,
    rejected,
    nextRefreshAt,
    exhausted: candidates.length > 0 && eligible === 0,
  };
}


function cloneInteractionState(state) {
  return {
    attempted: state?.attempted && typeof state.attempted === "object" ? { ...state.attempted } : {},
  };
}

function interactionKey(protocol, candidateId) {
  return `${protocol || "mtproto"}:${candidateId}`;
}

export function markAttempted(state, candidateId, protocol = "mtproto", atIso = new Date().toISOString()) {
  const next = cloneInteractionState(state);
  const key = interactionKey(protocol, candidateId);
  if (!next.attempted[key]) next.attempted[key] = atIso;
  return next;
}

export function isAttempted(state, candidateId, protocol = "mtproto") {
  return Boolean(state?.attempted?.[interactionKey(protocol, candidateId)]);
}

export function loadInteractionState(storage) {
  try {
    const raw = storage.getItem("proxy-interaction-state-v1");
    if (!raw) return { attempted: {} };
    return cloneInteractionState(JSON.parse(raw));
  } catch {
    return { attempted: {} };
  }
}

export function saveInteractionState(storage, state) {
  storage.setItem("proxy-interaction-state-v1", JSON.stringify(cloneInteractionState(state)));
}

function latestFeedbackKind(state, id) {
  const event = (state?.events ?? []).find(e => e.id === id);
  return event?.kind ?? null;
}

export function transportProgress(candidates, feedbackState, interactionState, protocol = "mtproto") {
  const scoped = candidates.filter(c => (c.protocol || "mtproto") === protocol);
  let attempted = 0;
  let working = 0;
  let remaining = 0;
  for (const candidate of scoped) {
    const kind = latestFeedbackKind(feedbackState, candidate.id);
    const opened = isAttempted(interactionState, candidate.id, protocol);
    if (opened) attempted += 1;
    if (kind === "good") working += 1;
    if (kind !== "bad" && kind !== "good" && !opened) remaining += 1;
  }
  return { attempted, working, remaining };
}


const VALID_TRANSPORTS = new Set(["mtproto", "socks5", "web"]);

export function activeTransport(storage) {
  const value = storage.getItem("proxy-active-transport-v1") || "mtproto";
  return VALID_TRANSPORTS.has(value) ? value : "mtproto";
}

export function setActiveTransport(storage, protocol) {
  const value = VALID_TRANSPORTS.has(protocol) ? protocol : "mtproto";
  storage.setItem("proxy-active-transport-v1", value);
}

export function candidatesForTransport(candidates, protocol = "mtproto") {
  const p = VALID_TRANSPORTS.has(protocol) ? protocol : "mtproto";
  return candidates.filter(c => (c.protocol || "mtproto") === p);
}
