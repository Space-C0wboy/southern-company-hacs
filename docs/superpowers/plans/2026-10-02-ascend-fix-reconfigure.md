# Ascend API Fix + Reconfigure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `southern_company` integration work again for Alabama/Georgia Power by vendoring the unreleased Ascend-API library fix (southern_company_api PR #24), and add a reconfigure flow for changing credentials in place.

**Architecture:** PR #24's `southern_company_api` package is copied into `custom_components/southern_company/_vendor/` and every integration import is pointed at it, so HA never loads the broken PyPI 0.7.1. A new `async_step_reconfigure` reuses the existing `_try_authenticate`. Shipped as tag `1.1.0-sc1` of the fork.

**Tech Stack:** Python 3.14, Home Assistant custom integration, `pytest-homeassistant-custom-component` in Docker (`python:3.14`).

**Spec:** `docs/superpowers/specs/2026-10-02-ascend-fix-reconfigure-design.md`

## Global Constraints

- Vendored source: `https://github.com/sng492/southern_company_api`, commit `bcbaa10d509f7ebc767085d9682da05acbcfe1a7`, directory `src/southern_company_api/`. Only change to vendored files: absolute self-imports → relative.
- Vendored path: `custom_components/southern_company/_vendor/southern_company_api/`.
- `manifest.json`: no `southern-company-api` requirement; `version` = `1.1.0-sc1`; `documentation`/`issue_tracker` → `https://github.com/Space-C0wboy/southern-company-hacs`.
- Reconfigure error codes = existing ones: `invalid_auth`, `cannot_connect`, `email_validation_required`, `unknown`. Success abort reason: `reconfigure_successful`. Duplicate username abort: `already_configured`.
- Do not change: the reauth flow, the 600 s robot-detection latch in `__init__.py`, Nicor Gas logic (imports only), statistics logic.
- This repo is public: no real usernames, account numbers or addresses in code, tests or docs. Use `user@example.com` / `other@example.com`.
- Tests run only via `scripts/test.sh` (Docker). Local Python is 3.13 and cannot run the HA harness.
- Git: work on branch `ascend-fix`; never push without owner approval. Commit messages end with a blank line + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

## File Structure

| File | Responsibility |
|---|---|
| `custom_components/southern_company/_vendor/__init__.py` (new, empty) | Makes `_vendor` a package |
| `custom_components/southern_company/_vendor/southern_company_api/*` (new, copied) | PR #24 library |
| `custom_components/southern_company/_vendor/southern_company_api/LICENSE` (new, copied) | Library's MIT licence |
| `custom_components/southern_company/_vendor/README.md` (new) | Provenance + removal condition |
| `custom_components/southern_company/{__init__,config_flow,coordinator,sensor,statistics}.py` (modify) | Imports → vendored package; config_flow gains reconfigure |
| `custom_components/southern_company/manifest.json` (modify) | Drop requirement, bump version, fork URLs |
| `custom_components/southern_company/strings.json`, `translations/en.json` (modify) | Reconfigure strings |
| `custom_components/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, `pytest.ini`, `requirements_test.txt`, `Dockerfile.test`, `scripts/test.sh`, `.gitattributes` (new) | Test harness |
| `tests/test_vendor.py`, `tests/test_config_flow.py` (new) | Tests |
| `README.md` (modify) | "About this fork" section |

---

### Task 1: Test harness + vendored library + import rewiring

**Files:**
- Create: `Dockerfile.test`, `requirements_test.txt`, `pytest.ini`, `scripts/test.sh`, `.gitattributes`, `custom_components/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_vendor.py`
- Create (copy): `custom_components/southern_company/_vendor/__init__.py`, `_vendor/southern_company_api/` (all files from the source dir), `_vendor/southern_company_api/LICENSE`, `_vendor/README.md`
- Modify: `custom_components/southern_company/__init__.py` (lines 8, 14, 60), `config_flow.py` (lines 9, 16, 72), `coordinator.py` (lines 11, 12, 15), `sensor.py` (line 10), `statistics.py` (lines 9, 10), `manifest.json`

**Interfaces:**
- Produces: package `custom_components.southern_company._vendor.southern_company_api` exposing the same names as PyPI's (`SouthernCompanyAPI`, `Account`, `NicorGasAPI`, `NicorUsageHistory`, submodules `account`, `parser`, `exceptions`, `nicor_parser`, `nicor_account`); `scripts/test.sh [pytest args]`.

- [ ] **Step 1: Create the test harness**

`requirements_test.txt`:
```
pytest-homeassistant-custom-component==0.13.368
```

`Dockerfile.test`:
```dockerfile
FROM python:3.14
COPY requirements_test.txt /tmp/requirements_test.txt
RUN pip install --no-cache-dir -r /tmp/requirements_test.txt
WORKDIR /src
```

`pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
testpaths = tests
pythonpath = .
```

`scripts/test.sh`:
```bash
#!/usr/bin/env bash
# Run the test suite in Docker (HA's test harness needs Python 3.14).
set -euo pipefail
cd "$(dirname "$0")/.."
docker build -q -f Dockerfile.test -t southern-company-test . >/dev/null
SRC="$(pwd -W 2>/dev/null || pwd)"
MSYS_NO_PATHCONV=1 docker run --rm -v "$SRC:/src" southern-company-test pytest -q "$@"
```
Then `git add` it and run `git update-index --chmod=+x scripts/test.sh` after the first commit-add.

`.gitattributes` — append (create if missing) these lines:
```
*.sh text eol=lf
Dockerfile* text eol=lf
```

`custom_components/__init__.py` and `tests/__init__.py`: empty files.

`tests/conftest.py`:
```python
"""Shared test fixtures."""
import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """Load custom_components/southern_company; the manifest depends on recorder."""
    yield
```

- [ ] **Step 2: Write the failing vendored-library test**

`tests/test_vendor.py`:
```python
"""The integration must use the vendored Ascend-API library, never PyPI's 0.7.1."""
import sys

VENDOR = "custom_components.southern_company._vendor.southern_company_api"


def test_vendored_package_is_importable_and_self_contained():
    from custom_components.southern_company._vendor import southern_company_api as lib

    assert lib.__name__ == VENDOR
    # parser.py's former absolute import must now resolve inside the vendored package
    assert lib.parser.Account is lib.account.Account
    assert lib.parser.Account.__module__ == f"{VENDOR}.account"


def test_integration_modules_import_the_vendored_library():
    from custom_components.southern_company import config_flow, coordinator, sensor, statistics
    from custom_components.southern_company._vendor import southern_company_api as lib

    assert config_flow.SouthernCompanyAPI is lib.SouthernCompanyAPI
    assert coordinator.southern_company_api is lib
    assert sensor.southern_company_api is lib
    assert statistics.southern_company_api is lib
    assert "southern_company_api" not in sys.modules  # PyPI package never imported
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `bash scripts/test.sh tests/test_vendor.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.southern_company._vendor'` (first run builds the image; allow ~5 min).

- [ ] **Step 4: Copy the library in**

```bash
git clone -q https://github.com/sng492/southern_company_api /tmp/scapi-vendor
git -C /tmp/scapi-vendor checkout -q bcbaa10d509f7ebc767085d9682da05acbcfe1a7
mkdir -p custom_components/southern_company/_vendor
cp -r /tmp/scapi-vendor/src/southern_company_api custom_components/southern_company/_vendor/
cp /tmp/scapi-vendor/LICENSE custom_components/southern_company/_vendor/southern_company_api/LICENSE
: > custom_components/southern_company/_vendor/__init__.py
find custom_components/southern_company/_vendor -name "__pycache__" -prune -exec rm -rf {} +
```
(On Windows Git Bash use a scratch dir instead of `/tmp` if paths are too long.)

Then rewrite the vendored absolute self-imports. Find them:
```bash
grep -rnE "^\s*(from|import) southern_company_api" custom_components/southern_company/_vendor/southern_company_api/
```
Expected: one hit, `parser.py: from southern_company_api.account import Account`. Change it to `from .account import Account`. If grep shows any others, convert each the same way (`from southern_company_api.X import Y` → `from .X import Y`). Change nothing else in the vendored files.

`custom_components/southern_company/_vendor/README.md`:
```markdown
# Vendored: southern_company_api (Ascend API port)

- Source: https://github.com/sng492/southern_company_api (branch `feat/ascend-api`)
- Upstream PR: https://github.com/Southern-Company-HA/southern_company_api/pull/24
- Commit: `bcbaa10d509f7ebc767085d9682da05acbcfe1a7`
- Licence: MIT (`southern_company_api/LICENSE`)
- Local changes: absolute self-imports rewritten as relative imports; nothing else.

Why: Southern Company moved the JWT to a response header and moved account/usage
data to the Ascend (OCC) hosts (upstream issue
https://github.com/Southern-Company-HA/southern-company-hacs/issues/141). The fix
is unreleased, and it still reports version 0.7.1, so a pinned requirement would
be treated as already satisfied by PyPI's broken 0.7.1.

Remove when: a `southern-company-api` release on PyPI includes the Ascend port.
Then delete this `_vendor/` directory, restore the requirement in
`manifest.json`, and point the imports back at `southern_company_api`.
```

- [ ] **Step 5: Rewire the integration's imports**

Exact replacements (keep everything else on each line):

`__init__.py`
- line 8: `from southern_company_api.exceptions import (` → `from ._vendor.southern_company_api.exceptions import (`
- line 14: `from southern_company_api.parser import SouthernCompanyAPI` → `from ._vendor.southern_company_api.parser import SouthernCompanyAPI`
- line 60: `from southern_company_api.nicor_parser import NicorGasAPI  # noqa: PLC0415` → `from ._vendor.southern_company_api.nicor_parser import NicorGasAPI  # noqa: PLC0415`

`config_flow.py`
- line 9: `from southern_company_api.exceptions import (` → `from ._vendor.southern_company_api.exceptions import (`
- line 16: `from southern_company_api.parser import SouthernCompanyAPI` → `from ._vendor.southern_company_api.parser import SouthernCompanyAPI`
- line 72: `from southern_company_api.nicor_parser import NicorGasAPI  # noqa: PLC0415` → `from ._vendor.southern_company_api.nicor_parser import NicorGasAPI  # noqa: PLC0415`

`coordinator.py`
- line 11: `import southern_company_api` → `from ._vendor import southern_company_api`
- line 12: `from southern_company_api.exceptions import SouthernCompanyException` → `from ._vendor.southern_company_api.exceptions import SouthernCompanyException`
- line 15: `    from southern_company_api.nicor_parser import NicorGasAPI` → `    from ._vendor.southern_company_api.nicor_parser import NicorGasAPI`

`sensor.py`
- line 10: `import southern_company_api` → `from ._vendor import southern_company_api`

`statistics.py`
- line 9: `import southern_company_api` → `from ._vendor import southern_company_api`
- line 10: `from southern_company_api.nicor_account import ...` → `from ._vendor.southern_company_api.nicor_account import ...` (same imported names)

Verify nothing non-vendored remains:
```bash
grep -rnE "^\s*(from|import) southern_company_api" custom_components/southern_company --include=*.py | grep -v "/_vendor/"
```
Expected: no output.

- [ ] **Step 6: Update `manifest.json`**

Set exactly:
```json
{
  "domain": "southern_company",
  "name": "Southern Company",
  "codeowners": ["@Lash-L", "@Space-C0wboy"],
  "config_flow": true,
  "dependencies": ["recorder"],
  "documentation": "https://github.com/Space-C0wboy/southern-company-hacs",
  "integration_type": "hub",
  "issue_tracker": "https://github.com/Space-C0wboy/southern-company-hacs/issues",
  "loggers": ["southern_company", "custom_components.southern_company._vendor.southern_company_api"],
  "quality_scale": "bronze",
  "requirements": [],
  "version": "1.1.0-sc1"
}
```

- [ ] **Step 7: Run the tests and confirm they pass**

Run: `bash scripts/test.sh tests/test_vendor.py`
Expected: 2 passed. Also run `python -m compileall -q custom_components/southern_company` (exit 0).

- [ ] **Step 8: Commit**

```bash
git add .gitattributes Dockerfile.test requirements_test.txt pytest.ini scripts/test.sh custom_components tests
git update-index --chmod=+x scripts/test.sh
git commit -m "feat: vendor the Ascend API library fix (southern_company_api PR #24)"
```

---

### Task 2: Reconfigure flow

**Files:**
- Modify: `custom_components/southern_company/config_flow.py` (add method to `ConfigFlow`), `strings.json`, `translations/en.json`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `ConfigFlow._try_authenticate(self, user_input: Mapping[str, Any], errors: dict[str, str]) -> None` (existing; sets `errors["base"]` on failure); `STEP_USER_DATA_SCHEMA` (existing module constant).
- Produces: `ConfigFlow.async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult`.

- [ ] **Step 1: Write the failing tests**

`tests/test_config_flow.py`:
```python
"""Tests for the reconfigure step."""
from unittest.mock import patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.southern_company.config_flow import ConfigFlow

DATA = {"username": "user@example.com", "password": "old", "account_type": "southern_company"}


def fake_auth(error: str | None = None):
    async def _try_authenticate(self, user_input, errors):
        if error:
            errors["base"] = error

    return _try_authenticate


@pytest.fixture(autouse=True)
def no_setup():
    with patch("custom_components.southern_company.async_setup_entry", return_value=True):
        yield


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(domain="southern_company", data=dict(DATA), title="Southern Company Hacs")
    entry.add_to_hass(hass)
    return entry


async def test_reconfigure_shows_prefilled_form(hass, entry):
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    username_key = next(k for k in result["data_schema"].schema if k == "username")
    assert username_key.description["suggested_value"] == "user@example.com"


async def test_reconfigure_updates_credentials(hass, entry):
    result = await entry.start_reconfigure_flow(hass)
    with patch.object(ConfigFlow, "_try_authenticate", fake_auth()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "user@example.com", "password": "new", "account_type": "southern_company"},
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["password"] == "new"


@pytest.mark.parametrize("error", ["invalid_auth", "cannot_connect", "email_validation_required", "unknown"])
async def test_reconfigure_errors_reshow_form(hass, entry, error):
    result = await entry.start_reconfigure_flow(hass)
    with patch.object(ConfigFlow, "_try_authenticate", fake_auth(error)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**DATA, "password": "bad"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert entry.data["password"] == "old"


async def test_reconfigure_rejects_username_of_another_entry(hass, entry):
    MockConfigEntry(domain="southern_company", data={**DATA, "username": "other@example.com"}).add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    with patch.object(ConfigFlow, "_try_authenticate", fake_auth()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**DATA, "username": "other@example.com"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["username"] == "user@example.com"
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `bash scripts/test.sh tests/test_config_flow.py`
Expected: FAIL — the flow aborts with `not_implemented` / unknown step `reconfigure` (no `async_step_reconfigure`).

- [ ] **Step 3: Implement `async_step_reconfigure`**

Add this method to `ConfigFlow` in `config_flow.py`, directly after `async_step_reauth_confirm`:
```python
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the credentials of an existing entry in place."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_USERNAME] != entry.data[CONF_USERNAME]:
                self._async_abort_entries_match(
                    {CONF_USERNAME: user_input[CONF_USERNAME]}
                )
            await self._try_authenticate(user_input, errors)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA,
                {
                    CONF_USERNAME: entry.data[CONF_USERNAME],
                    CONF_ACCOUNT_TYPE: entry.data.get(
                        CONF_ACCOUNT_TYPE, ACCOUNT_TYPE_SOUTHERN_COMPANY
                    ),
                },
            ),
            errors=errors,
        )
```

- [ ] **Step 4: Add the strings**

`strings.json` — inside `config.step`, after `reauth_confirm`, add:
```json
      "reconfigure": {
        "title": "Update credentials",
        "description": "Change the username and/or password this integration signs in with.",
        "data": {
          "username": "[%key:common::config_flow::data::username%]",
          "password": "[%key:common::config_flow::data::password%]",
          "account_type": "Account type"
        }
      }
```
and inside `config.abort` add:
```json
      "reconfigure_successful": "[%key:common::config_flow::abort::reconfigure_successful%]"
```

`translations/en.json` — inside `config.step`, after `reauth_confirm`, add:
```json
            "reconfigure": {
                "title": "Update credentials",
                "description": "Change the username and/or password this integration signs in with.",
                "data": {
                    "password": "Password",
                    "username": "Username",
                    "account_type": "Account type"
                }
            }
```
and inside `config.abort` add:
```json
            "reconfigure_successful": "Re-configuration was successful"
```
Both files must remain valid JSON: `python -c "import json;json.load(open('custom_components/southern_company/strings.json'));json.load(open('custom_components/southern_company/translations/en.json'))"`.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `bash scripts/test.sh`
Expected: all pass (2 vendor + 7 config flow = 9).

- [ ] **Step 6: Commit**

```bash
git add custom_components/southern_company/config_flow.py custom_components/southern_company/strings.json custom_components/southern_company/translations/en.json tests/test_config_flow.py
git commit -m "feat: reconfigure flow to change credentials in place"
```

---

### Task 3: README "About this fork"

**Files:**
- Modify: `README.md` (insert at the very top, before existing content)

- [ ] **Step 1: Insert the section**

```markdown
> ## About this fork
>
> This is a fork of [Southern-Company-HA/southern-company-hacs](https://github.com/Southern-Company-HA/southern-company-hacs)
> that works again for Alabama Power / Georgia Power after Southern Company's
> September 2026 API changes ([upstream #141](https://github.com/Southern-Company-HA/southern-company-hacs/issues/141)).
>
> - Bundles the unreleased Ascend-API library fix
>   ([southern_company_api#24](https://github.com/Southern-Company-HA/southern_company_api/pull/24))
>   under `custom_components/southern_company/_vendor/` — see the README there.
> - Adds a **Reconfigure** option to change the username/password without
>   deleting the integration.
>
> **Install:** in HACS remove the upstream "Southern Company HACS" repository,
> add `https://github.com/Space-C0wboy/southern-company-hacs` as a custom
> repository (category: Integration), install the latest release and restart.
> Your existing config entry and statistics are kept.
>
> **Switch back** to upstream once it publishes a release containing the
> Ascend fix.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: explain the fork in the README"
```

---

### Task 4: Release + deploy (OWNER-CONFIRMED STEPS)

**Files:** none. Acts on GitHub, HA and the desktop Docker host. Every step needs an explicit "yes" from the owner in chat before it runs.

- [ ] **Step 1: Merge to the fork's `main`, tag, release**

```bash
git checkout main && git merge --no-ff ascend-fix -m "Merge ascend-fix: Ascend API fix + reconfigure"
bash scripts/test.sh
git push origin main
git tag -a 1.1.0-sc1 -m "1.1.0-sc1" && git push origin 1.1.0-sc1
gh release create 1.1.0-sc1 --repo Space-C0wboy/southern-company-hacs --title "1.1.0-sc1 — Ascend API fix + reconfigure" --notes "Works again for Alabama/Georgia Power after Southern Company's Sept 2026 API changes (upstream #141). Bundles southern_company_api PR #24; adds a Reconfigure flow."
```

- [ ] **Step 2: Switch HACS to the fork**

With ha-mcp: `ha_manage_hacs(action="remove", repository_id="Southern-Company-HA/southern-company-hacs")` (the config entry is kept), then `ha_manage_hacs(action="add_repository", repository="Space-C0wboy/southern-company-hacs", category="integration")`, then `ha_manage_hacs(action="download", repository_id="Space-C0wboy/southern-company-hacs", version="1.1.0-sc1")`. If HACS hides `1.1.0-sc1` as a pre-release, re-tag as `1.1.1` and repeat Step 1's tag/release lines.

- [ ] **Step 3: Restart and enable**

`ha_restart(confirm=True)`; wait until the API answers; `ha_set_integration(entry_id="01KMNX1TXRBN4MZ5PM21KSMAE6", enabled=True)`.

- [ ] **Step 4: Verify (stop on first failure; never retry login in a loop)**

- `ha_get_integration(entry_id=...)` → `state: loaded`. If `setup_error`/`setup_retry`, read `ha_get_logs(source="error_log", search="southern")`, then disable the entry again before investigating.
- The electric account's sensors (search `ha_search(query="southern_company")` / the entry's entities) have non-unavailable values.
- `ha_get_history(source="statistics", entity_ids="southern_company:energy_usage_<electric account number>", period="day", start_time="30d")` returns rows (backfill can take a few minutes).

- [ ] **Step 5: Retire the sidecar and record it**

`docker stop utility-auth-sidecar && docker update --restart=no utility-auth-sidecar` (keep the image for now). Update the Claude memory `utility-auth-sidecar.md` and `BACKLOG.md` in the Home-Assistant repo.
