import assert from "node:assert/strict";
import {
  recencyWeight,
  recordFeedback,
  selectBatch,
  workingReserve,
  rejectBatch,
} from "./learning.js";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;
const now = Date.parse("2026-10-04T18:00:00Z");

assert.equal(recencyWeight(new Date(now - (6 * HOUR - 1)).toISOString(), now), 1.0);
assert.equal(recencyWeight(new Date(now - 6 * HOUR).toISOString(), now), 0.8);
assert.equal(recencyWeight(new Date(now - 24 * HOUR).toISOString(), now), 0.5);
assert.equal(recencyWeight(new Date(now - 3 * DAY).toISOString(), now), 0.25);
assert.equal(recencyWeight(new Date(now - (7 * DAY + 1)).toISOString(), now), 0.1);

const candidate = {
  id: "abc123",
  source: "dubblebyte handshake",
  port: "8443",
  kind: "ee",
  domain: "aysghfkzcxg.info",
  secret: "secret-1",
};

let state = { events: [], stats: {} };
state = recordFeedback(state, candidate, "good", "2026-10-04T17:55:00Z");

for (const key of [
  "id:abc123",
  "source:dubblebyte handshake",
  "port:8443",
  "kind:ee",
  "domain:aysghfkzcxg.info",
  "secret:secret-1",
]) {
  assert.equal(state.stats[key].good, 1, "missing good aggregate for " + key);
}

for (let i = 0; i < 510; i++) {
  state = recordFeedback(state, { ...candidate, id: "id-" + i }, "bad", new Date(now - i * 1000).toISOString());
}
assert.equal(state.events.length, 500, "event history must be capped at 500");

console.log("learning tests OK");


const candidates = Array.from({ length: 20 }, (_, i) => ({
  id: "c" + i,
  source: i < 8 ? "known-good" : "new-source-" + i,
  port: i < 8 ? "8443" : String(9000 + i),
  kind: i < 8 ? "ee" : "other",
  domain: i < 8 ? "known.example" : "new" + i + ".example",
  secret: i < 8 ? "known-secret" : "s" + i,
}));

let rankedState = { events: [], stats: {} };
for (let i = 0; i < 8; i++) {
  rankedState = recordFeedback(rankedState, candidates[i], "good", "2026-10-04T17:50:00Z");
}
rankedState = recordFeedback(rankedState, candidates[19], "bad", "2026-10-04T17:55:00Z");

const batch = selectBatch(candidates, rankedState, 10, now);
assert.equal(batch.length, 10, "batch must contain 10 candidates");
assert.equal(batch.filter(x => x.source === "known-good").length, 8, "expected 8 exploitation candidates");
assert.equal(batch.filter(x => x.source !== "known-good").length, 2, "expected 2 exploration candidates");
assert.ok(!batch.some(x => x.id === "c19"), "known bad candidate must not reappear");

const goodTopState = recordFeedback(rankedState, candidates[0], "good", "2026-10-04T17:59:00Z");
const batch2 = selectBatch(candidates, goodTopState, 10, now);
assert.equal(batch2[0].id, "c0", "exact confirmed good should rank first");
assert.equal(batch2.filter(x => x.source !== "known-good").length, 2, "good exact match must not consume exploration slots");

console.log("batch selection tests OK");


let reserveState = { events: [], stats: {} };
const working = {
  id: "working-1",
  server: "m.aysghfkzcxg.info",
  port: "8443",
  source: "dubblebyte handshake",
  kind: "ee",
  domain: "aysghfkzcxg.info",
  secret: "good-secret",
};
const dead = { ...working, id: "dead-1", server: "dead.example", domain: "dead.example", secret: "dead-secret" };
reserveState = recordFeedback(reserveState, working, "good", "2026-10-04T17:00:00Z");
reserveState = rejectBatch(reserveState, [working, dead], ["working-1", "dead-1"], "2026-10-04T17:10:00Z");
assert.equal((reserveState.events.find(e => e.id === "working-1") || {}).kind, "good", "batch reject must not overwrite a working proxy");
assert.equal((reserveState.events.find(e => e.id === "dead-1") || {}).kind, "bad", "batch reject must mark unconfirmed proxy bad");

reserveState = recordFeedback(reserveState, working, "good", "2026-10-04T17:30:00Z");
const older = { ...working, id: "working-old", server: "old.example", domain: "old.example", secret: "old-secret" };
reserveState = recordFeedback(reserveState, older, "good", "2026-09-24T17:00:00Z");

const reserve = workingReserve(reserveState, {}, now);
assert.equal(reserve[0].id, "working-1", "most recent working proxy should be first");
assert.equal(reserve[0].goodCount, 2, "repeat confirmations must be counted");
assert.equal(reserve.find(x => x.id === "working-old").ageBand, "stale", "working entries older than 7 days remain but are stale");

console.log("working reserve tests OK");
