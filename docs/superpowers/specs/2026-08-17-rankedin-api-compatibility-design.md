# Rankedin API compatibility and local runtime design

## Goal

Restore the Padel Dashboard after Rankedin changed JSON property names from PascalCase to camelCase, while retaining compatibility with existing cached responses. Make the project reproducibly runnable from a local Windows virtual environment.

## Scope

- Support both the old and new Rankedin response shapes in all four API parsers: team matches, individual match details, lineups, and standings.
- Preserve the DataFrame schemas consumed by the dashboard, statistics, and lineup optimizer.
- Add automated regression tests for both property-name conventions.
- Improve the top-level data-loading error so a response-schema problem is distinguishable from an HTTP or endpoint failure.
- Add a local `.venv`, install the declared dependencies, and ensure generated environment and bytecode files are ignored by Git.
- Verify the data pipeline and that Streamlit starts successfully.

## Design

### Compatibility boundary

Add one small lookup helper in `padel_pipeline.py`. Given a mapping and a logical property name, it will accept the PascalCase form used by old cache files and the camelCase form now returned by Rankedin. Required properties raise a descriptive schema error that includes the expected property and the keys actually received. Optional properties retain their existing defaults.

Only the Rankedin parsing functions use this helper. They continue returning exactly the same internal snake_case columns as before, so downstream code does not change.

### Parser coverage

Update these functions without changing their public signatures:

- `parse_team_matches`
- `parse_individual_matches`
- `parse_lineup`
- `parse_standings`

Nested objects and collections use the same compatibility lookup. Parsing remains strict for required data so malformed responses are reported instead of silently producing incorrect statistics.

### Caching

Both existing PascalCase cache files and newly downloaded camelCase files remain readable. Cache files are treated as runtime data and are not rewritten merely to change key casing.

### Error handling

Separate fetch failures from parse/schema failures in the message surfaced by `build_dataset`. The message must include the original exception detail and avoid claiming that the URL is wrong when the HTTP request succeeded.

The existing tolerant behavior for optional match details, lineups, standings, and availability remains unchanged: those components may be empty while the main dashboard continues when team matches were parsed successfully.

## Tests

Use the standard-library `unittest` framework to avoid adding a test dependency. Tests will use minimal representative dictionaries rather than network calls.

Required regression cases:

- Team matches parse from old PascalCase JSON.
- Team matches parse from new camelCase JSON.
- Individual match details parse from both conventions.
- Lineups parse from both conventions.
- Standings parse from both conventions.
- Missing required properties produce a descriptive schema error.

The new-format team-match test must fail against the current implementation before production code is changed.

## Local environment

Create `.venv` under the project directory with an available Python runtime and install `requirements.txt`. Add `.venv/`, `__pycache__/`, `*.pyc`, and Streamlit runtime artifacts to `.gitignore`. Existing tracked cache data will not be deleted as part of this fix.

If creating the environment or installing dependencies is blocked by local permissions or network access, request the required approval and report the exact blocked step.

## Verification

Completion requires fresh evidence from:

1. The complete automated test suite.
2. Python compilation of all project modules.
3. A pipeline execution against the available cached/current data.
4. A bounded Streamlit startup showing that the server reaches its ready state without an import or initialization error.
5. `git diff` and `git status` review confirming that only intended source, test, documentation, and ignore-file changes remain.

## Non-goals

- Redesigning the dashboard UI.
- Changing statistics or lineup-optimization behavior.
- Replacing the cache architecture.
- Updating season/team configuration beyond what is necessary to run the current configured season.
