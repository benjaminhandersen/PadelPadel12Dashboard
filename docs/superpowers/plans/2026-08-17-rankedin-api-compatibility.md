# Rankedin API Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the dashboard by accepting both Rankedin's former PascalCase JSON and current camelCase JSON, and provide a reproducible local Windows runtime.

**Architecture:** Keep Rankedin compatibility at the parsing boundary through one strict mapping lookup helper. Preserve every downstream snake_case DataFrame contract, cover both response conventions with standard-library tests, and leave network access out of unit tests.

**Tech Stack:** Python 3.12, `unittest`, pandas, requests, Streamlit, openpyxl, Windows PowerShell

## Global Constraints

- Support both the old and new Rankedin response shapes in all four API parsers.
- Preserve the DataFrame schemas consumed by the dashboard, statistics, and lineup optimizer.
- Use only standard-library `unittest`; do not add a test dependency.
- Existing tracked cache data must not be deleted.
- Do not redesign the UI or change statistics and lineup-optimization behavior.
- Required missing properties must raise a descriptive schema error rather than silently returning incorrect data.

---

### Task 1: Reproducible local runtime

**Files:**
- Create: `.gitignore`
- Create locally, do not commit: `.venv/`
- Verify: `requirements.txt`

**Interfaces:**
- Consumes: bundled Python executable at `C:\Users\benja\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
- Produces: `.venv\Scripts\python.exe` with every package in `requirements.txt`

- [ ] **Step 1: Add generated-file exclusions**

```gitignore
.venv/
__pycache__/
*.py[cod]
.streamlit/secrets.toml
```

- [ ] **Step 2: Create the virtual environment**

Run:

```powershell
& 'C:\Users\benja\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
```

Expected: exit code 0 and `.venv\Scripts\python.exe` exists.

- [ ] **Step 3: Install declared dependencies**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
```

Expected: exit code 0; pandas, requests, Streamlit, and openpyxl install successfully.

- [ ] **Step 4: Verify imports and ignore behavior**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -c "import pandas, requests, streamlit, openpyxl; print('runtime imports ok')"
git check-ignore .venv/Scripts/python.exe __pycache__/example.pyc .streamlit/secrets.toml
```

Expected: `runtime imports ok`; all three generated paths are printed by `git check-ignore`.

- [ ] **Step 5: Commit the runtime configuration**

```powershell
git add .gitignore
git commit -m "chore: add reproducible local Python environment"
```

### Task 2: Team-match casing compatibility

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_rankedin_parsers.py`
- Modify: `padel_pipeline.py:130-159`

**Interfaces:**
- Produces: `_rankedin_get(mapping: dict, pascal_name: str, default: object = _MISSING) -> object`
- Preserves: `parse_team_matches(raw: dict, our_team_id: int) -> pandas.DataFrame`

- [ ] **Step 1: Write the failing camelCase team-match test**

Create a `unittest.TestCase` with a literal response containing `matches`, `team1`, `team2`, `details`, `matchId`, `showResults`, `result`, `isWinner`, and the configured team ID. Assert the returned row equals these hand-checked values:

```python
self.assertEqual(result.loc[0, "team_match_id"], 137894)
self.assertEqual(result.loc[0, "round"], 1)
self.assertEqual(result.loc[0, "opponent"], "TTPK MIX")
self.assertEqual(result.loc[0, "our_score"], 4)
self.assertEqual(result.loc[0, "their_score"], 2)
self.assertTrue(bool(result.loc[0, "won"]))
```

Add a second test using the same hand-written values with PascalCase keys and assert the same observable row contract.

- [ ] **Step 2: Run the tests and verify the new-format case fails for the confirmed reason**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_rankedin_parsers -v
```

Expected: PascalCase passes; camelCase errors with `KeyError: 'Matches'`.

- [ ] **Step 3: Add the strict compatibility helper**

In `padel_pipeline.py`, add a private sentinel and helper near the parsing section:

```python
_MISSING = object()


def _rankedin_get(mapping: dict, pascal_name: str, default=_MISSING):
    camel_name = pascal_name[:1].lower() + pascal_name[1:]
    if pascal_name in mapping:
        return mapping[pascal_name]
    if camel_name in mapping:
        return mapping[camel_name]
    if default is not _MISSING:
        return default
    available = ", ".join(sorted(map(str, mapping.keys())))
    raise KeyError(
        f"Rankedin-svaret mangler '{pascal_name}'/'{camel_name}'. "
        f"Tilgængelige felter: {available or '(ingen)'}"
    )
```

Replace every direct external-key access in `parse_team_matches` with `_rankedin_get`, including nested team and details mappings. Keep the existing snake_case output column names unchanged.

- [ ] **Step 4: Verify both casing conventions pass**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_rankedin_parsers -v
```

Expected: both team-match tests pass.

- [ ] **Step 5: Add and verify the required-property error test**

Add a test that calls `parse_team_matches({}, 2701885)` and asserts the exception contains `Matches`, `matches`, and `Tilgængelige felter`. Run the test module again and expect all cases to pass.

- [ ] **Step 6: Commit team-match compatibility**

```powershell
git add tests/__init__.py tests/test_rankedin_parsers.py padel_pipeline.py
git commit -m "fix: accept both Rankedin team-match key formats"
```

### Task 3: Match-detail, lineup, and standings compatibility

**Files:**
- Modify: `tests/test_rankedin_parsers.py`
- Modify: `padel_pipeline.py:162-260`

**Interfaces:**
- Consumes: `_rankedin_get(mapping, pascal_name, default)` from Task 2
- Preserves: `parse_individual_matches`, `parse_lineup`, and `parse_standings` signatures and output schemas

- [ ] **Step 1: Write failing camelCase tests for each remaining parser**

Add literal minimal fixtures for:

- An individual match with `matches.matches`, `challenger`, `challenged`, `matchResult.score`, and one `detailedScoring` set. Assert player names, `sets_str == "6-4"`, `games_diff == 2`, and `won is True`.
- A lineup with `firstTeam`, `secondTeam`, one player, and one `rankingTypePoints` entry. Assert the returned name, ranking points, and `role == "Captain"`.
- Standings with one `scoresViewModels` entry. Assert participant ID, match points, games difference, and position.

For each fixture, add a PascalCase counterpart asserting the same behavior. Derive expected values literally rather than through production helpers.

- [ ] **Step 2: Run tests and verify only camelCase cases fail**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_rankedin_parsers -v
```

Expected: the three new camelCase cases fail on their first old-format key; PascalCase cases pass.

- [ ] **Step 3: Apply `_rankedin_get` throughout the remaining parsers**

Replace all direct Rankedin-key reads in:

```python
parse_individual_matches(raw, team_match_id, we_are_challenger)
parse_lineup(raw, our_team_id)
parse_standings(raw)
```

Use `default=[]` for optional `DetailedScoring` and optional ranking-point lists. Keep zero values and `False` values distinct from missing values. Do not rename internal output columns.

- [ ] **Step 4: Run the full parser suite**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_rankedin_parsers -v
```

Expected: all old- and new-format parser cases pass with no warnings or errors.

- [ ] **Step 5: Commit remaining parser support**

```powershell
git add tests/test_rankedin_parsers.py padel_pipeline.py
git commit -m "fix: support camelCase Rankedin parser responses"
```

### Task 4: Data-loading diagnostics and integration verification

**Files:**
- Create: `tests/test_pipeline_errors.py`
- Modify: `padel_pipeline.py:360-373`
- Verify: `dashboard.py`, `pages/1_Holdforslag.py`

**Interfaces:**
- Preserves: `build_dataset(our_team_id=OUR_TEAM_ID, pool_id=OUR_POOL_ID, refresh=False) -> dict`
- Produces: distinct error context for fetch failures and team-match schema failures

- [ ] **Step 1: Write a failing schema-error integration test**

Use `unittest.mock.patch` only at the external `fetch` boundary so the real `build_dataset` and parser execute:

```python
with patch("padel_pipeline.fetch", return_value={}):
    with self.assertRaisesRegex(RuntimeError, "(?i)(parse.*Rankedin|format)"):
        build_dataset()
```

Assert that the resulting message contains the original missing-property detail and does not claim `url_team_matches()` is probably wrong.

- [ ] **Step 2: Run the error test and verify it fails against the misleading current message**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_pipeline_errors -v
```

Expected: failure because the current message says the URL is probably wrong.

- [ ] **Step 3: Separate fetch and parse failures in `build_dataset`**

Use one `try` block around `fetch` that raises `RuntimeError("Kunne ikke hente holdkampe fra Rankedin...")`, followed by a separate `try` block around `parse_team_matches` that raises `RuntimeError("Kunne ikke parse holdkampe fra Rankedin; svarformatet er ændret eller ugyldigt...")`. Chain the original exception in both cases and preserve its text.

- [ ] **Step 4: Run all automated tests and compilation**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -m py_compile app_config.py padel_pipeline.py player_stats.py lineup_optimizer.py dashboard.py pages\1_Holdforslag.py
```

Expected: all tests pass; compilation exits 0 with no output.

- [ ] **Step 5: Exercise the real pipeline**

Run:

```powershell
& '.\.venv\Scripts\python.exe' padel_pipeline.py
```

Expected: exit code 0; team matches are parsed from the current camelCase cache. Optional external availability failure may be reported only if network access is unavailable, without terminating the pipeline.

- [ ] **Step 6: Perform a bounded Streamlit startup check**

Run Streamlit headlessly on an unused local port, wait for the ready message, request its health endpoint, then stop only that recorded process:

```powershell
$padelProcess = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList '-m','streamlit','run','dashboard.py','--server.headless=true','--server.port=8517' -WindowStyle Hidden -PassThru
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8517/_stcore/health
Stop-Process -Id $padelProcess.Id
```

Expected: health endpoint returns HTTP 200 and body `ok`.

- [ ] **Step 7: Review scope and commit diagnostics/tests**

Run:

```powershell
git diff --check
git status --short
git diff --stat HEAD~3
```

Confirm only `.gitignore`, parser code, tests, and the approved docs changed. Then commit:

```powershell
git add padel_pipeline.py tests/test_pipeline_errors.py
git commit -m "fix: clarify Rankedin schema errors"
```

- [ ] **Step 8: Run fresh final verification after the commit**

Repeat the complete test discovery, compilation, real pipeline run, Streamlit health check, and final `git status --short`. Record exact pass counts and any remaining external-service warnings for the handoff.
