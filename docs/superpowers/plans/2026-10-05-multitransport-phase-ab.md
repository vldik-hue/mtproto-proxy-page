# Multi-Transport Proxy Radar Phase A+B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the radar usable for high-volume manual testing by marking attempted proxies, showing progress, and adding a small SOCKS5 diagnostic mode while preserving the existing MTProto workflow.

**Architecture:** Keep GitHub Pages + GitHub Actions. Extend the browser-side state machine to distinguish unseen / attempted / working / bad, and scope state by transport. Add a transport-aware candidate/link model in `learning.js`; keep `update_page.py` responsible for generating candidate metadata and HTML. Phase A ships attempted tracking and corrected MTProto labels; Phase B adds a deliberately small SOCKS5 diagnostic pool. WEB remains gated behind a validated endpoint source and client compatibility check, handled by a separate plan/spike after A+B.

**Tech Stack:** Python 3 standard library, vanilla JavaScript ES modules, browser localStorage, Node.js tests, GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-10-05-multitransport-proxy-radar.md`

## Global Constraints

- Keep the service at 0 ₽.
- Do not embed tokens, passwords, PATs, or other private secrets in the public page.
- Preserve the fixed three-button footer.
- Attempted and working are separate states.
- Attempted state must persist across reloads.
- Working state must never be downgraded by attempted state or batch rejection.
- Progress counters are scoped to the active transport.
- MTProto TCP reachability must be labeled only as a network reachability signal, not Telegram usability.
- SOCKS5 rollout is diagnostic only: target 5–10 candidates.
- Do not add a massive SOCKS5 feed if the diagnostic batch yields zero user-confirmed successes.
- WEB implementation is not shipped until the exact client import format and endpoint source are validated.
- Existing MTProto feedback history and working reserve must remain usable.

## Review Focus

1. **Repeated taps:** tapping the same candidate multiple times must count as one attempted candidate; Task 1 tests unique-ID progress.
2. **Working preservation:** attempted marking or batch rejection must never overwrite a working proxy; Task 1 and Task 3 test both paths.
3. **Transport isolation:** MTProto and SOCKS5 counters/history must not leak into each other; Task 2 tests separate namespaces.
4. **Legacy migration:** existing MTProto localStorage ratings must remain visible after the state model changes; Task 1 tests migration.
5. **Credential safety:** SOCKS5 username/password may be public proxy credentials but must be URL-encoded correctly and never be mistaken for application secrets; Task 3 tests link encoding and no token literals.

---

### Task 1: Attempted State and Progress Counters

**Files:**
- Modify: `learning.js`
- Modify: `test_learning.mjs`
- Modify: `update_page.py`
- Modify: `test_ui.py`

**Interfaces:**
- Consumes: existing candidate IDs, feedback state, localStorage.
- Produces:
  - `markAttempted(state, candidateId, protocol, atIso) -> state`
  - `isAttempted(state, candidateId, protocol) -> boolean`
  - `transportProgress(candidates, feedbackState, interactionState, protocol) -> {attempted, working, remaining}`
  - `loadInteractionState(storage) -> state`
  - `saveInteractionState(storage, state) -> void`

- [ ] **Step 1: Write failing tests for attempted state**

Assertions:
- first attempt records one unique ID;
- second attempt of same ID does not increment unique count;
- attempted state survives save/load;
- a candidate already working remains working after attempted marking;
- existing MTProto good/bad feedback still loads independently of interaction state.

- [ ] **Step 2: Run RED**

Run: `node test_learning.mjs`

Expected: FAIL because attempted-state functions do not exist.

- [ ] **Step 3: Implement attempted-state functions in `learning.js`**

Use a dedicated storage key such as `proxy-interaction-state-v1`. Key attempted IDs by protocol + candidate ID.

- [ ] **Step 4: Add click interception for the primary “Проверить” action**

Before navigating to the proxy deep link:
- record attempted state;
- save it;
- repaint the card;
- then allow the link handoff to Telegram.

Do not mark it working automatically.

- [ ] **Step 5: Add attempted visual state**

Generated page must expose:
- a CSS class such as `.attempted`;
- a badge/text hook showing `↗ Открыт`.

- [ ] **Step 6: Add top progress text**

For active MTProto view render:

`Открыто N · Работает M · Осталось K`

Counts use unique current-catalog IDs.

- [ ] **Step 7: Extend UI tests**

Assert:
- attempted class/badge hook exists;
- progress copy exists;
- primary action has a stable attempt hook;
- existing three footer controls remain.

- [ ] **Step 8: Verify GREEN**

Run:
- `python3 update_page.py`
- `python3 test_ui.py`
- `node test_learning.mjs`

Expected: all PASS.

- [ ] **Step 9: Commit**

`git add learning.js test_learning.mjs update_page.py test_ui.py && git commit -m "feat: track attempted proxies and progress"`

---

### Task 2: Transport-Scoped State and Tabs

**Files:**
- Modify: `learning.js`
- Modify: `test_learning.mjs`
- Modify: `update_page.py`
- Modify: `test_ui.py`

**Interfaces:**
- Consumes: attempted state, feedback state, candidate metadata.
- Produces:
  - candidate field `protocol: "mtproto" | "socks5" | "web"`
  - `activeTransport(storage) -> string`
  - `setActiveTransport(storage, protocol) -> void`
  - `candidatesForTransport(candidates, protocol) -> Candidate[]`

- [ ] **Step 1: Write failing transport-isolation tests**

Assertions:
- marking MTProto candidate attempted does not change SOCKS5 progress;
- working MTProto candidate does not appear in SOCKS5 working reserve;
- active transport persists through localStorage;
- unknown protocol falls back to `mtproto`.

- [ ] **Step 2: Run RED**

Run: `node test_learning.mjs`

Expected: FAIL on missing transport helpers.

- [ ] **Step 3: Implement transport helpers**

Keep MTProto as default for backward compatibility.

- [ ] **Step 4: Add compact transport tabs**

Render:
- `MTProto`
- `SOCKS5`
- `WEB`

For Phase A+B:
- MTProto enabled;
- SOCKS5 enabled once candidates exist;
- WEB shown as `WEB · скоро` or disabled until Phase C validation.

- [ ] **Step 5: Scope rendering and footer actions to active transport**

Batch rejection and working reserve operate only on candidates of the selected protocol.

- [ ] **Step 6: Verify GREEN**

Run:
- `python3 update_page.py`
- `python3 test_ui.py`
- `node test_learning.mjs`

Expected: all PASS.

- [ ] **Step 7: Commit**

`git add learning.js test_learning.mjs update_page.py test_ui.py && git commit -m "feat: scope proxy radar by transport"`

---

### Task 3: Small SOCKS5 Diagnostic Pool

**Files:**
- Modify: `update_page.py`
- Modify: `learning.js`
- Modify: `test_learning.mjs`
- Modify: `test_ui.py`

**Interfaces:**
- Consumes: transport-aware candidate model.
- Produces:
  - `buildProxyLink(candidate) -> string`
  - SOCKS5 candidate records with `protocol="socks5"`, `server`, `port`, optional `user`, optional `pass`, `source`
  - initial SOCKS5 candidate cap = 10.

- [ ] **Step 1: Write failing SOCKS5 link tests**

Known fixture without credentials:
- server `1.2.3.4`
- port `1080`
- expected prefix `tg://socks?server=1.2.3.4&port=1080`

Known fixture with credentials:
- username/password containing spaces and symbols;
- assert they are URL-encoded and mapped to `user` / `pass`.

- [ ] **Step 2: Run RED**

Run: `node test_learning.mjs`

Expected: FAIL because `buildProxyLink` does not support SOCKS5.

- [ ] **Step 3: Implement `buildProxyLink(candidate)`**

MTProto:
- `tg://proxy?server=...&port=...&secret=...`

SOCKS5:
- `tg://socks?server=...&port=...&user=...&pass=...`
- omit optional credential parameters when absent.

- [ ] **Step 4: Add a SOCKS5 collector with a hard cap of 10 published candidates**

Source acceptance rules:
- explicit SOCKS5 records only;
- current/fresh source preferred;
- de-duplicate exact server:port:credentials;
- do not reuse MTProto TCP verification semantics as proof of Telegram usability.

If no source yields candidates, render the SOCKS5 tab with a clear “нет диагностических кандидатов” state rather than inventing entries.

- [ ] **Step 5: Add network reachability pre-filter only where useful**

If a SOCKS5 endpoint is pre-filtered via TCP connect, label it `TCP доступен`, not `Telegram проверен`.

- [ ] **Step 6: Extend UI tests**

Assert:
- SOCKS5 tab exists;
- no more than 10 SOCKS5 cards are generated;
- SOCKS5 cards use the SOCKS deep-link builder;
- MTProto metadata copy says `TCP доступен` rather than implying Telegram success.

- [ ] **Step 7: Verify GREEN**

Run:
- `python3 update_page.py`
- `python3 test_ui.py`
- `node test_learning.mjs`

Expected: all PASS.

- [ ] **Step 8: Commit**

`git add update_page.py learning.js test_learning.mjs test_ui.py && git commit -m "feat: add small SOCKS5 diagnostic pool"`

---

### Task 4: Diagnostic Decision State

**Files:**
- Modify: `learning.js`
- Modify: `test_learning.mjs`
- Modify: `update_page.py`

**Interfaces:**
- Consumes: per-transport progress and feedback.
- Produces:
  - `diagnosticStatus(protocol, progress, feedbackState) -> {status, message}`

- [ ] **Step 1: Write failing diagnostic-status tests**

Assertions:
- SOCKS5 with at least one working candidate => `success`;
- SOCKS5 with all diagnostic candidates rejected and zero working => `failed`;
- partially tested SOCKS5 => `testing`;
- MTProto status does not automatically trigger more candidate volume after hundreds of failures.

- [ ] **Step 2: Run RED**

Run: `node test_learning.mjs`

Expected: FAIL on missing diagnostic status.

- [ ] **Step 3: Implement diagnostic status**

When SOCKS5 diagnostic pool is exhausted with zero good:
- display “SOCKS5 не прошёл контрольный тест — не расширяем перебор; переходим к WEB”.

Do not automatically fetch hundreds more SOCKS5 entries.

- [ ] **Step 4: Verify GREEN**

Run full suite.

Expected: all PASS.

- [ ] **Step 5: Commit**

`git add learning.js test_learning.mjs update_page.py && git commit -m "feat: add transport diagnostic decision state"`

---

### Task 5: Final Branch Verification

**Files:**
- Modify only if verification reveals a defect.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: deployable Phase A+B branch.

- [ ] **Step 1: Run complete suite**

Run:
- `python3 update_page.py`
- `python3 test_ui.py`
- `node test_learning.mjs`

Expected: all exit 0.

- [ ] **Step 2: Verify generated HTML**

Check:
- attempted marker and styling present;
- progress summary present;
- MTProto / SOCKS5 / WEB tabs present;
- MTProto says TCP reachability only;
- SOCKS5 candidate count <= 10;
- no secret application tokens in HTML.

- [ ] **Step 3: Verify GitHub Actions on branch**

Expected:
- Build page success;
- Test UI success;
- Test learning success.

- [ ] **Step 4: Manual smoke path**

Sequence:
1. open MTProto candidate;
2. confirm its card becomes attempted;
3. reload page and confirm attempted marker persists;
4. mark one proxy working and confirm attempted/reject actions do not downgrade it;
5. switch SOCKS5 and test one candidate;
6. confirm counters are transport-scoped.

- [ ] **Step 5: Stop before WEB implementation**

WEB gets a separate validation step/plan because current client support and public endpoint availability must be proven before shipping a link generator.

