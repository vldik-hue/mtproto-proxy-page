import assert from "node:assert/strict";
import {
  recencyWeight,
  recordFeedback,
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
