# Adaptive MTProto Learning — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing MTProto page into a reliable local-learning radar that uses recency, exploration, and a persistent working-proxy reserve while keeping the current 10-at-a-time mobile workflow.

**Architecture:** Keep GitHub Actions as the remote pool generator and GitHub Pages as the static delivery layer. Move ranking/learning rules into a small browser-side module with pure functions so they can be tested independently; the generated page provides proxy metadata and UI, while localStorage remains the feedback store.

**Tech Stack:** Python 3 standard library, vanilla JavaScript ES modules, browser localStorage, Node.js for pure-function tests, GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-10-04-proxy-radar-design.md`

## Global Constraints

- Keep the service at 0 ₽ and do not add a paid backend.
- Do not embed GitHub PATs, Telegram tokens, passwords, or other secrets in the public page.
- Preserve the current mobile flow: 10 candidates at a time and the fixed three-button footer.
- Working proxies must never be overwritten by batch rejection.
- TCP reachability remains only a pre-filter, not proof that Telegram works for the user.
- Keep automatic pool refresh every 2 hours and the manual “Новый пул” action.
- Phase 1 remains MTProto-only; SOCKS5 and Web Proxy are separate later plans.
- Keep at most 500 detailed local feedback events.
- Local learning may reset if browser localStorage is cleared; that is accepted for Phase 1.

## Review Focus

1. **Clock/age boundaries:** exactly 6h, 24h, 3d, and 7d must map to deterministic decay buckets; Task 1 tests these boundaries.
2. **Conflicting feedback:** an exact proxy previously marked good must remain good when its current batch is rejected; Task 3 tests this regression.
3. **Overfitting:** a batch must still include exploratory candidates when enough alternatives exist; Task 2 tests the 7–8 exploitation / 2–3 exploration requirement.
4. **Stale working reserve:** old good proxies remain visible but rank below recent confirmations; Task 3 tests ordering by last successful timestamp.
5. **Exhausted pool:** once all candidates are rejected, the UI must not recycle them or alert-loop; Task 4 tests the stable empty state and refresh guidance.

---

### Task 1: Extract and Test the Local Learning Model

**Files:**
- Create: `learning.js`
- Create: `test_learning.mjs`
- Modify: `.github/workflows/update-page.yml`

**Interfaces:**
- Consumes: candidate metadata already emitted by `update_page.py`.
- Produces:
  - `recencyWeight(isoTime, nowMs) -> number`
  - `featureScore(stats, weight, nowMs) -> number`
  - `candidateScore(candidate, feedbackState, nowMs) -> number`
  - `recordFeedback(state, candidate, kind, atIso) -> state`
  - `loadFeedback(storage) -> state`
  - `saveFeedback(storage, state) -> void`

- [ ] **Step 1: Write failing tests for recency and feedback aggregation in `test_learning.mjs`**

Assertions:
- age < 6h => weight 1.0
- 6h–24h => 0.8
- 1–3d => 0.5
- 3–7d => 0.25
- >7d => 0.1
- one `good` event increments exact id, source, port, kind, domain and secret aggregates
- event history is capped at 500 entries

- [ ] **Step 2: Run the test and verify RED**

Run: `node test_learning.mjs`

Expected: FAIL because `learning.js` exports do not yet exist.

- [ ] **Step 3: Implement the pure learning functions in `learning.js`**

Use plain objects only; no DOM dependencies in the pure scoring/recording functions. Positive evidence must be stronger than one negative event. Apply recency as a multiplier to event-derived confidence.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `node test_learning.mjs`

Expected: PASS with no uncaught errors.

- [ ] **Step 5: Add `node test_learning.mjs` to the GitHub Actions workflow**

Place it after page generation and before commit/push.

- [ ] **Step 6: Run the existing and new test commands**

Run:
- `python3 update_page.py`
- `python3 test_ui.py`
- `node test_learning.mjs`

Expected: all exit 0.

- [ ] **Step 7: Commit**

`git add learning.js test_learning.mjs .github/workflows/update-page.yml && git commit -m "feat: extract testable proxy learning model"`

---

### Task 2: Add Exploration-Aware Batch Selection

**Files:**
- Modify: `learning.js`
- Modify: `test_learning.mjs`
- Modify: `update_page.py`

**Interfaces:**
- Consumes: `candidateScore(candidate, feedbackState, nowMs)`.
- Produces:
  - `selectBatch(candidates, feedbackState, size, nowMs) -> Candidate[]`

- [ ] **Step 1: Write failing tests for exploitation/exploration mix**

For a pool of at least 20 eligible candidates:
- batch size is 10;
- 7 or 8 come from the highest-scoring known patterns;
- 2 or 3 come from candidates with weak/no local evidence;
- candidates already marked bad do not appear;
- an exact proxy marked good may appear at the top but must not consume all exploration slots.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node test_learning.mjs`

Expected: FAIL on missing/incorrect `selectBatch`.

- [ ] **Step 3: Implement `selectBatch`**

Use deterministic selection, not randomness, so tests and UI ordering are reproducible. Prefer 8 exploitation + 2 exploration when enough candidates exist; fall back gracefully when either group is too small.

- [ ] **Step 4: Integrate batch selection into the generated page**

Replace current simple `.sort(...).slice(...)` logic with the exported selector. Preserve the existing 10-at-a-time UI and local rejection behavior.

- [ ] **Step 5: Verify GREEN**

Run:
- `node test_learning.mjs`
- `python3 update_page.py`
- `python3 test_ui.py`

Expected: all PASS.

- [ ] **Step 6: Commit**

`git add learning.js test_learning.mjs update_page.py && git commit -m "feat: balance learned ranking with exploration"`

---

### Task 3: Build a Durable Working-Proxy Reserve

**Files:**
- Modify: `learning.js`
- Modify: `test_learning.mjs`
- Modify: `update_page.py`
- Modify: `test_ui.py`

**Interfaces:**
- Consumes: feedback state and candidate metadata.
- Produces:
  - `workingReserve(feedbackState, candidateCatalog, nowMs) -> WorkingProxy[]`
  - each working entry includes `id`, `server`, `port`, `source`, `lastGoodAt`, `goodCount`, and age band.

- [ ] **Step 1: Write failing regression tests**

Assertions:
- marking proxy good then rejecting its visible batch leaves it good;
- two good confirmations increment `goodCount`;
- reserve sorts by most recent successful confirmation, then confirmation count;
- entries older than 7 days remain present but report a stale age band.

- [ ] **Step 2: Run tests and verify RED**

Run: `node test_learning.mjs`

Expected: FAIL on missing reserve behavior.

- [ ] **Step 3: Implement reserve derivation in `learning.js`**

Do not create a second source of truth; derive the reserve from persisted feedback plus current catalog metadata.

- [ ] **Step 4: Update the “⭐ Рабочие” view**

Show compact rows with:
- server:port;
- source;
- “работал: сегодня / вчера / N дней назад”;
- confirmation count.

Do not show rejected proxies in this view.

- [ ] **Step 5: Extend `test_ui.py`**

Assert that the generated page keeps the “⭐ Рабочие” control and includes reserve metadata placeholders/hooks.

- [ ] **Step 6: Verify GREEN**

Run:
- `node test_learning.mjs`
- `python3 update_page.py`
- `python3 test_ui.py`

Expected: all PASS.

- [ ] **Step 7: Commit**

`git add learning.js test_learning.mjs update_page.py test_ui.py && git commit -m "feat: add persistent working proxy reserve"`

---

### Task 4: Make Pool Exhaustion Stable and Actionable

**Files:**
- Modify: `learning.js`
- Modify: `test_learning.mjs`
- Modify: `update_page.py`
- Modify: `test_ui.py`

**Interfaces:**
- Consumes: current pool candidate IDs and local feedback state.
- Produces:
  - `poolStatus(candidates, feedbackState, generatedAt, nowMs) -> {eligible, rejected, nextRefreshAt, exhausted}`

- [ ] **Step 1: Write failing tests for exhausted-pool state**

Assertions:
- when all current pool IDs are bad, `exhausted === true`;
- no previously rejected ID is selected again;
- `nextRefreshAt` is the next 2-hour refresh boundary after `generatedAt`;
- repeated rendering of exhausted state performs no alert loop and does not reset ratings.

- [ ] **Step 2: Run tests and verify RED**

Run: `node test_learning.mjs`

Expected: FAIL on missing `poolStatus`.

- [ ] **Step 3: Implement `poolStatus`**

Keep the function pure. The page uses the returned state to render messaging.

- [ ] **Step 4: Replace the current exhausted-pool message**

Render:
- “Все кандидаты этого пула проверены”;
- number rejected;
- approximate next automatic refresh time;
- visible “🔄 Новый пул” action.

Do not recycle the pool.

- [ ] **Step 5: Extend `test_ui.py`**

Assert the generated page contains the stable exhausted-state copy and still has the three-button footer.

- [ ] **Step 6: Verify full Phase 1 suite**

Run:
- `python3 update_page.py`
- `python3 test_ui.py`
- `node test_learning.mjs`

Expected: all PASS and no warnings/errors that affect execution.

- [ ] **Step 7: Commit**

`git add learning.js test_learning.mjs update_page.py test_ui.py && git commit -m "feat: stabilize exhausted pool workflow"`

---

### Task 5: End-to-End Workflow Verification

**Files:**
- Modify only if verification exposes a defect.

**Interfaces:**
- Consumes: all outputs from Tasks 1–4.
- Produces: verified deployable Phase 1 build.

- [ ] **Step 1: Run the complete local-equivalent suite**

Run:
- `python3 update_page.py`
- `python3 test_ui.py`
- `node test_learning.mjs`

Expected: all exit 0.

- [ ] **Step 2: Trigger or observe the GitHub Actions workflow on the final commit**

Expected:
- Build page: success
- Test UI: success
- Learning tests: success
- Commit fresh page: success or “No page changes”

- [ ] **Step 3: Verify the deployed HTML contains the Phase 1 controls and no secret material**

Check:
- three footer controls;
- learning summary;
- working reserve hook;
- no GitHub token / Telegram token literal.

- [ ] **Step 4: Manually validate the user flow on the page**

Sequence:
1. open one candidate;
2. mark it good;
3. reject the rest of the batch;
4. verify the good proxy remains in “⭐ Рабочие”;
5. verify the next batch contains exploration candidates;
6. exhaust a test pool and verify it does not loop.

- [ ] **Step 5: Record any discovered defects as separate bug tasks before Phase 2**

Do not start SOCKS5 work until Phase 1 is verified.

- [ ] **Step 6: Commit verification-only fixes if needed**

Use one focused commit per defect.
