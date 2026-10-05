# Multi-Transport Proxy Radar — Design

## Goal

Restore practical Telegram connectivity as quickly as possible by turning the existing page into a diagnostic radar that can test multiple proxy transports instead of endlessly cycling through MTProto candidates that may all be blocked by the user's network.

The system must also clearly track which proxy candidates the user has already attempted so large batches do not become confusing or repetitive.

## Success Criteria

1. Every candidate the user opens in Telegram is visibly marked as attempted.
2. Attempted state persists across page reloads on the same browser/device.
3. "Attempted" and "Works" are separate states.
4. The top of the page shows progress counts: attempted, working, remaining.
5. The radar supports separate transport modes:
   - MTProto
   - SOCKS5
   - Web Proxy
6. MTProto TCP reachability is not presented as proof that Telegram works.
7. SOCKS5 is introduced first as a small control batch, not as another huge blind list.
8. Web Proxy is added only from sources/formats that expose the correct Telegram-compatible connection parameters.
9. If public transports all fail, the next fallback is a local HTTPS/WebSocket bridge rather than more brute-force MTProto enumeration.
10. Existing local feedback and the working-proxy reserve are preserved.

## Scope

This design covers:

- attempted/opened candidate tracking;
- progress counters;
- transport tabs;
- MTProto labeling cleanup;
- a small SOCKS5 diagnostic pool;
- a Web Proxy diagnostic path;
- fallback architecture toward a local WebSocket/HTTPS bridge.

This design does not yet define a centralized feedback backend.

## 1. Attempted State

### Behavior

When the user presses the primary action on a candidate:

- record an "attempted" event immediately before handing off to Telegram;
- visually change the card;
- add a persistent badge, e.g. "↗ Открыт";
- keep the candidate visible until the user explicitly marks it working or rejects the batch.

"Attempted" means only that the candidate was sent to Telegram.

"Working" means the user explicitly confirmed that Telegram connected through it.

### Persistence

Store attempted state in localStorage using the candidate ID.

Recommended state model:

- unseen
- attempted
- working
- bad

The current feedback state remains the authority for working/bad classification. Attempted state is an additional interaction flag and must never downgrade a working proxy.

## 2. Visual Treatment

Candidate states:

- unseen: normal white card;
- attempted: light muted background + "↗ Открыт" badge;
- working: green success badge;
- bad: hidden from normal selection after rejection.

The visual difference between unseen and attempted must be obvious enough for rapid phone testing.

## 3. Progress Summary

At the top of the active transport view, show compact progress:

"Открыто 37 · Работает 0 · Осталось 163"

Counts are scoped to the active transport.

Definitions:

- Opened = unique candidate IDs attempted in the current catalog.
- Works = unique current-catalog candidate IDs whose latest state is good.
- Remaining = current eligible candidates never attempted and not bad.

Do not count repeated taps multiple times.

## 4. Transport Tabs

Top-level compact tabs:

- MTProto
- SOCKS5
- WEB

Each tab has:

- its own candidate list;
- independent progress counts;
- independent local statistics;
- separate working reserve entries.

The active tab is remembered locally.

## 5. MTProto Changes

Keep the existing MTProto collector and local-learning logic, but correct the meaning of the server-side verification.

Current external pre-filter:

- DNS/socket reachability;
- TCP connect success;
- latency measurement.

This must be labeled as "TCP доступен" or equivalent, not "Telegram проверен".

Real usability remains determined only by the user's explicit feedback.

Do not spend further effort expanding MTProto volume until another positive MTProto result appears.

## 6. SOCKS5 Diagnostic Pool

Purpose: determine whether SOCKS5 can traverse the user's current network.

Initial rollout:

- small pool only;
- target 5–10 fresh candidates;
- prioritize recently updated sources and explicit SOCKS5 entries;
- do not generate hundreds.

Candidate model:

- protocol = socks5
- server
- port
- optional username
- optional password
- source
- fetched_at
- optional external health metadata

Telegram handoff format must be generated from Telegram's supported SOCKS link parameters.

Success condition:

- at least one user-confirmed working SOCKS5 proxy.

If the initial diagnostic pool yields zero working results, do not scale the SOCKS5 search blindly; move priority to WEB.

## 7. Web Proxy Diagnostic Path

Purpose: test a transport that looks like real HTTPS/Web traffic rather than standard MTProto traffic.

Requirements:

- only ingest entries with Telegram-compatible Web Proxy parameters;
- validate the exact link/import format against the Telegram client behavior before publishing candidates;
- distinguish Web Proxy from generic HTTP/HTTPS forward proxies.

The radar must not label a generic web proxy as Telegram Web Proxy unless its parameters are actually usable by Telegram.

Initial rollout should be intentionally small.

## 8. Source Strategy

Source priority becomes transport-specific.

### MTProto
Keep existing sources but downgrade raw TCP verification to a weak health signal.

### SOCKS5
Prefer:
- actively maintained lists;
- recent timestamps;
- explicit SOCKS5 scheme or structured fields;
- duplicate removal.

### WEB
Prefer:
- projects specifically implementing Telegram Web Proxy;
- published compatible endpoints;
- documented server + secret/import parameters.

Do not merge generic HTTP proxy lists into WEB.

## 9. Ranking

Within a transport:

1. current user-confirmed working entries;
2. recent candidates from historically successful patterns;
3. unattempted exploratory candidates;
4. previously attempted but unresolved candidates;
5. stale/weak candidates.

An attempted-but-unresolved candidate should rank below unseen candidates so the user naturally moves forward instead of accidentally reopening the same proxy.

## 10. Bottom Controls

Keep the current 3-button footer:

- ❌ 10 не работают
- ⭐ Рабочие
- 🔄 Новый пул

Behavior is scoped to the active transport.

Batch rejection:

- working entries remain working;
- other visible candidates become bad;
- attempted state may remain in history.

## 11. Working Reserve

Working reserve must include protocol.

Example:

"⭐ SOCKS5 · host:port · работал сегодня · 2×"

Do not mix different transports without a visible protocol label.

## 12. Local Bridge Fallback

If:
- MTProto diagnostic pool = zero working;
- SOCKS5 diagnostic pool = zero working;
- public Web Proxy options = unavailable or zero working;

then stop public-proxy brute force.

Next architecture:

- local client-side or local-machine bridge;
- outbound HTTPS/WebSocket;
- no dependence on Telegram being reachable directly;
- no paid VPS as the default path.

This fallback requires a separate implementation plan because installation, OS behavior, autostart, and trust/security differ from the static radar.

## 13. Testing

Automated tests must cover:

- clicking/opening a candidate records attempted state;
- attempted state survives reload;
- attempted state never overwrites working;
- attempted card receives visible styling and badge;
- progress counts count unique IDs only;
- progress is transport-scoped;
- attempted unresolved candidates rank below unseen candidates;
- bottom batch rejection preserves working candidates;
- MTProto UI says TCP reachable rather than Telegram verified;
- SOCKS5 and Web candidate link builders produce expected Telegram-compatible URLs for known fixtures;
- transport tabs keep independent state.

## 14. Rollout Order

Phase A:
- attempted state;
- visual marker;
- progress counts;
- MTProto labeling correction.

Phase B:
- transport tabs;
- small SOCKS5 diagnostic pool.

Phase C:
- validated Web Proxy diagnostic path.

Phase D:
- only if all public transports fail: local HTTPS/WebSocket bridge.

## Non-Goals

- Paid VPS.
- Massive blind SOCKS5 enumeration.
- Calling TCP reachability "working Telegram".
- Treating generic HTTP proxies as Telegram Web Proxy.
- Global cloud feedback backend in this phase.
- Automatically marking a proxy working without explicit user confirmation.
