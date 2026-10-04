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
