# Fork: Ascend API fix + reconfigure flow

**Date:** 2026-10-02
**Status:** Approved design, pending implementation plan
**Repo:** `Space-C0wboy/southern-company-hacs` (fork of `Southern-Company-HA/southern-company-hacs`)

## Background

Southern Company changed its customer-service backend in late August / early
September 2026 (upstream issue #141). The integration's auth chain has three
steps, and two of them broke:

1. **Login → ScWebToken** — response shape changed. Fixed upstream on `main`
   by #122 (2026-09-10).
2. **ScWebToken → JWT** — `GET /Account/LoginValidated/JwtToken` now answers
   `200 {"Message":"Successfully retrieved jwtToken."}` with the token in a bare
   `ScJwtToken` **response header** instead of `Set-Cookie`. The library only
   reads cookies → `NoJwtTokenFound: Failed to get JWT: No cookies were sent back.`
3. **Data APIs** — `customerservice2api.southerncompany.com/api/...` is retired
   (401 for a valid JWT). Account and usage data moved to the "Ascend" (OCC)
   hosts `occaccountapi.southerncompany.com` and
   `occmypowerusageapi.southerncompany.com`.

Library PR `Southern-Company-HA/southern_company_api#24` (author `sng492`,
branch `feat/ascend-api`, head `bcbaa10d509f7ebc767085d9682da05acbcfe1a7`)
fixes 2 and 3. It is open and unmerged; PyPI is still at `0.7.1` and this
integration pins `southern-company-api==0.7.1`, so nothing installable through
HACS works for Alabama/Georgia Power today.

**Verified for an Alabama Power account (2026-10-02)** with a one-shot probe
(`scripts/probe_ascend.py`) against PR #24: login ✅, JWT ✅, accounts ✅
(two found; one without a service agreement is skipped), month-to-date ✅,
daily ✅. Hourly over the most recent 3 days returned no rows — expected, as
the last ~72 h are reported as delayed; the integration requests 31-day hourly
windows and falls back to daily on first setup.

The integration also has no **reconfigure** step: credentials can only be
changed through reauth (which upstream added in #122) or by delete + re-add.

## Decisions

1. **Base the fork on upstream `main`** (`2da7f8d`), which already carries the
   #122 login fix and the reauth flow.
2. **Vendor PR #24's library inside the integration** rather than pinning a
   `git+https://…` requirement. PR #24 still declares version `0.7.1`; HA
   already has PyPI `0.7.1` installed, so its requirement check would consider
   a pinned git requirement satisfied and never install the fix.
3. **Add a reconfigure step** that changes username and/or password in place.
4. **Release as a tag** (`1.1.0-sc1`) so HACS installs a version, not a branch.

Rejected: waiting for upstream (no release since 2024-08; unknown timeline);
patching the library inside HA's container (wiped by every HA update,
untracked).

## Changes

### 1. Vendored library

- Copy `src/southern_company_api/` from PR #24 at `bcbaa10` to
  `custom_components/southern_company/_vendor/southern_company_api/`, with an
  empty `custom_components/southern_company/_vendor/__init__.py`.
- Keep the library's MIT `LICENSE` beside it
  (`_vendor/southern_company_api/LICENSE`) and add
  `_vendor/README.md` stating the source repo, PR, commit and the removal
  condition (below).
- Rewrite the library's own absolute self-imports to relative imports
  (e.g. `parser.py`: `from southern_company_api.account import Account` →
  `from .account import Account`). No other code changes to the vendored files.
- Change every integration import of `southern_company_api` (in
  `__init__.py`, `config_flow.py`, `coordinator.py`, `sensor.py`,
  `statistics.py`) to the vendored package, e.g.
  `from ._vendor import southern_company_api` /
  `from ._vendor.southern_company_api.parser import SouthernCompanyAPI`.
- `manifest.json`: remove `southern-company-api==0.7.1` from `requirements`
  (aiohttp and PyJWT, the library's only dependencies, ship with HA); set
  `version` to `1.1.0-sc1`; point `documentation` / `issue_tracker` at the fork.
- **Removal condition:** when upstream publishes a `southern-company-api`
  release containing the Ascend port, delete `_vendor/`, restore the PyPI
  requirement, and (ideally) switch HACS back to upstream.

### 2. Reconfigure step (`config_flow.py`)

- New `async_step_reconfigure(user_input)`:
  - Form fields: username (pre-filled from the entry), password, account type
    (pre-filled; same selector as the user step).
  - Validates with the existing `_try_authenticate(user_input, errors)` — same
    error codes as the user/reauth steps (`invalid_auth`, `cannot_connect`,
    `email_validation_required`, `unknown`).
  - On success: `self.async_update_reload_and_abort(entry, data_updates=user_input)`.
  - Guard: if the new username differs from the entry's and another entry of
    this domain already uses it, abort `already_configured` (mirrors the user
    step's `_async_abort_entries_match`).
- `strings.json` and `translations/en.json`: add `config.step.reconfigure`
  (title, description, field labels) and `config.abort.reconfigure_successful`.
- Reauth flow: unchanged from upstream.

### 3. Docs

- `README.md`: a short "About this fork" section at the top — why it exists
  (#141), what it changes, how to install it as a HACS custom repository, and
  when to switch back.

## Out of scope

- The Playwright auth sidecar (this integration never used it upstream; it
  will be retired separately).
- The 600-second "Delaying retrying to prevent robot detection" latch in
  `__init__.py` — kept as-is; it protects against Imperva IP bans (#96).
- Nicor Gas paths — untouched apart from the import rewiring.
- Any upstream contribution (e.g. commenting on #141 / PR #24) — only if the
  owner asks.

## Testing

- **Static:** `python -m compileall custom_components/southern_company` and a
  grep proving no non-vendored `southern_company_api` import remains.
- **Unit (Docker, `python:3.14` + `pytest-homeassistant-custom-component`):**
  config-flow tests for reconfigure — success updates the entry and returns
  `reconfigure_successful`; `invalid_auth` / `cannot_connect` re-show the form
  with the error; duplicate username aborts `already_configured`.
  `_try_authenticate` is patched; no network.
- **Vendored-library smoke test:** import `SouthernCompanyAPI` and `Account`
  from the vendored path and assert the module is the vendored one, not a
  site-packages copy.
- **Live (owner's HA):** install the fork via HACS custom repository at tag
  `1.1.0-sc1`, restart, enable the entry; expect it to load, the four sensors
  to populate for the electric account, and `southern_company:energy_*`
  statistics to backfill. A failure must stop after one attempt (reauth on bad
  credentials; the latch on token errors) — never a retry loop.

## Rollout

1. Implement on branch `ascend-fix`; tests green.
2. Merge to the fork's `main`, tag `1.1.0-sc1`, publish a GitHub release
   (owner approval).
3. HACS: remove the upstream repository, add the fork as a custom
   repository (category Integration), install `1.1.0-sc1`, restart
   (owner approval).
4. Enable the config entry; verify sensors + statistics.
5. Retire the sidecar container; update memory and `BACKLOG.md`.
