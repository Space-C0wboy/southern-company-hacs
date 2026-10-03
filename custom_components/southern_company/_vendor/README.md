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
