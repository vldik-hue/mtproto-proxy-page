# Adaptive Proxy Radar — Design

## Goal

Build a free, low-friction Telegram connectivity radar that learns from the user's real network results and increasingly prioritizes proxy candidates that are more likely to work, while avoiding overfitting to one proxy family or one transport.

The system must remain useful even when Telegram itself is unavailable.

## Success Criteria

1. The user can test candidates quickly in batches of 10 with minimal scrolling.
2. Positive and negative feedback changes subsequent ordering immediately on the same device.
3. The system learns from:
   - exact proxy identity;
   - source;
   - port;
   - secret/type;
   - domain/family;
   - recency of feedback.
4. Known working proxies are preserved and can be revisited separately.
5. New pools refresh automatically every 2 hours and can also be refreshed manually.
6. The system explores alternatives instead of getting trapped in one family.
7. The design supports multiple Telegram proxy transports:
   - MTProto first;
   - SOCKS5 next;
   - Web Proxy after that.
8. No paid backend is required for the initial version.
9. No secret token is embedded into the public GitHub Pages site.

## Current Architecture

- GitHub Pages hosts a static page.
- GitHub Actions regenerates the candidate pool.
- Public sources are fetched and candidates are filtered/verified.
- The browser stores local feedback in localStorage.
- Candidates are shown 10 at a time.
- User actions:
  - “✅ Работает” for an individual proxy;
  - “❌ 10 не работают” for the rest of the current batch;
  - “⭐ Рабочие” to revisit locally confirmed good proxies;
  - “🔄 Новый пул” to open the GitHub workflow for a manual refresh.
- Automatic pool refresh runs every 2 hours.

## Proposed Architecture

### 1. Candidate Model

Every candidate should have a normalized record:

- id
- protocol: mtproto | socks5 | web
- server
- port
- secret or credentials when applicable
- source
- domain_family
- transport_type / secret_type
- verifier_latency_ms
- fetched_at
- source_verified_at if available
- local_feedback:
  - good_count
  - bad_count
  - last_good_at
  - last_bad_at

The browser does not need to persist the full remote record forever; it only needs enough metadata to score future candidates.

### 2. Local Learning Model

The browser keeps local feedback statistics for these feature groups:

- exact proxy id
- source
- port
- protocol
- secret/type
- domain family

Each feedback event is stored with a timestamp.

A positive event should increase confidence more strongly than one negative event decreases it, because a single real success on the user's ISP is highly informative.

### 3. Recency Decay

Feedback must decay with age.

Example policy:

- 0–6 hours: full weight
- 6–24 hours: 0.8
- 1–3 days: 0.5
- 3–7 days: 0.25
- older than 7 days: 0.1

Exact values may be tuned later, but the core rule is required: a proxy or family that worked recently should outrank one that worked long ago.

### 4. Ranking

Each candidate receives a local score.

Recommended feature weights:

- exact proxy success: very high
- exact secret/type success: high
- domain family success: high
- source success: medium-high
- port success: medium
- protocol success: medium
- external verifier latency: weak tie-breaker only
- recency: multiplier

Negative evidence reduces the score.

The ranking must avoid treating TCP reachability as equivalent to real Telegram usability.

### 5. Exploration vs Exploitation

Do not show only the highest-scoring family.

Each 10-candidate batch should contain approximately:

- 7–8 candidates from the best-scoring known patterns;
- 2–3 exploratory candidates from new or weakly tested patterns.

This protects against stale learning and operator-side changes.

### 6. Working Proxy Reserve

A dedicated “⭐ Рабочие” view should show locally confirmed working proxies with:

- server:port
- protocol
- source
- last successful timestamp
- number of successful confirmations

Working proxies must never be overwritten as bad merely because the rest of their batch is rejected.

Old working entries remain visible but visually age over time.

### 7. Multi-Protocol UI

Top-level compact tabs:

- MTProto
- SOCKS5
- Web

Initial rollout order:

1. MTProto — keep current behavior.
2. SOCKS5 — add a separate candidate source and separate learning statistics.
3. Web Proxy — add only after confirming the exact Telegram client behavior and import format.

Protocol statistics are independent.

Example compact summary:

“MTProto 2/57 · SOCKS5 0/10 · best port 8443”

### 8. Mobile UI

Primary requirement: fast thumb operation.

Bottom fixed controls remain one row:

- ❌ 10 не работают
- ⭐ Рабочие
- 🔄 Новый пул

Candidate cards stay compact.

Each card has only:

- number
- server:port
- protocol/type/source metadata
- ▶ Проверить
- ✅ Работает

Avoid extra explanatory text in the main testing flow.

### 9. Pool Generation

GitHub Actions continues to generate the remote candidate catalog every 2 hours.

For the initial no-backend version:

- GitHub creates a larger verified catalog;
- the browser performs the final user-specific ranking locally;
- local feedback survives normal page reloads on the same device/browser.

This means GitHub does not yet learn from local feedback globally, but the user's page does.

### 10. Source Quality

Sources should be classified by verification strength:

Tier A:
- real MTProto/SOCKS handshake or equivalent protocol-level verification;
- freshness timestamp;
- active maintenance.

Tier B:
- reliable curated regional list;
- regular refresh;
- some practical evidence.

Tier C:
- raw TCP-only or stale aggregate lists.

Default selection order:
Tier A → Tier B → Tier C fallback.

Sources with repeated local failures should be deprioritized, not permanently banned.

### 11. Data Retention

Local feedback event log:

- keep the latest 500 events;
- keep aggregate feature statistics;
- keep working proxy history separately.

If localStorage is cleared, learning resets. That limitation is accepted for the first version.

### 12. Failure Handling

If all current candidates are rejected:

- show “Все кандидаты этого пула проверены”;
- do not loop back to already rejected entries;
- show when the next automatic refresh is expected;
- keep the manual “Новый пул” action available.

If a source fetch fails:

- continue with remaining sources;
- show no user-facing failure unless the final candidate count becomes too small.

### 13. Testing

Automated tests should verify:

- 3-button bottom control layout;
- working proxy is not overwritten by batch rejection;
- scoring prefers recent positive feedback;
- negative feedback lowers score;
- exploration candidates remain present;
- rejected candidates do not reappear within the same pool;
- tabs keep separate protocol statistics;
- empty pool state is stable and does not alert-loop.

### 14. Deferred Global Feedback Backend

Not part of the first implementation.

Future option:
- external free backend stores feedback centrally;
- GitHub generator can use cross-device history before publishing the next pool.

This phase requires a separate design because it changes trust, privacy, persistence, and public-write security.

## Implementation Boundaries

Phase 1:
- strengthen local learning;
- add recency;
- add exploration;
- improve working reserve;
- keep MTProto.

Phase 2:
- add SOCKS5.

Phase 3:
- investigate and add Web Proxy if Telegram import behavior is suitable.

Phase 4:
- optional centralized feedback backend.

## Non-Goals

- Paid VPS hosting.
- Embedding GitHub PATs or other secrets into the public page.
- Automatically changing Telegram settings without user action.
- Treating externally reachable TCP as proof of Telegram usability.
- Removing all exploration in favor of one previously successful family.
