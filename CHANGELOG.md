# Changelog

All notable changes to ToolProof.

## 0.5.1 — cross-repo integration + review hardening

### Added

- `tests/test_cross_repo_integration.py` — pytest version of the mtg/scripts/cross_repo_smoke.sh flow. Exercises `guard_tool` → `receipt_from_mtg_run` on each Hurmoz dialect-specialized send_message variant, asserts receipt dialect_expected, outcome, and tamper detection. Skips gracefully when mtg/hurmoz not locatable.
- `integration` pytest marker registered in `pyproject.toml`.

### Changed

- `Receipt.sign()` now produces **two** hashes: the legacy-core hash (0.4.x-compatible, covers tool/args/response/error/ts) and `evidence_hash` (covers MTG fields: outcome, hash_prev, dialect_expected/observed, arabic_preserved, arg_integrity_score, mtg_violations). Tampering either region after signing breaks `verify_integrity()`. Previously MTG fields were silently mutable post-sign — this closes the integrity gap.
- `mtg_bridge.receipt_from_mtg_run` now reads each guard's attached `spec` dict (ValidationReport propagates it), so `dialect_expected` is pulled from the correct Arabic slot and `dialect_observed` is filtered to Arabic-declared slots instead of falling back to any non-unknown dialect.
- `pyproject.toml` adds explicit `[tool.setuptools.packages.find]` include/exclude to avoid picking up sibling content/, downloads/, openclaw/ directories.

### Fixed

- Evidence hash regression — MTG integrity fields were not previously covered by the signature. Shipping v0.5.1 to mark the hardening.

## 0.5.0 — MTG integration

### Added

- `toolproof.mtg_bridge` module with:
  - `from_mtg_violation(violation, tool, call_id=None, prev_receipt_hash=None, ...)` — convert a single MTG violation into a signed Receipt. Maps `high` → `fail`, `medium` → `partial`, `low`/`info` → `pass`.
  - `receipt_from_mtg_run(tool, guards, ...)` — build a comprehensive receipt from a full MTG pipeline run, aggregating per-parameter guard results, computing `arg_integrity_score`, and extracting `dialect_observed` and `arabic_preserved`.
  - `SEVERITY_TO_OUTCOME` mapping table.
- `Receipt` gains the following optional fields (all additive, all default `None`/empty, backward-compatible):
  - `outcome: Optional[str]` — `'pass' | 'partial' | 'fail'`
  - `hash_prev: Optional[str]` — previous-receipt hash for MTG hash chain
  - `dialect_expected: Optional[str]`
  - `dialect_observed: Optional[str]`
  - `arabic_preserved: Optional[bool]`
  - `arg_integrity_score: Optional[float]` (0.0 – 1.0)
  - `mtg_violations: list[dict]` (serialized MTG Violations)
- New tests in `tests/test_mtg_bridge.py` (9 tests) covering severity mapping, worst-outcome aggregation, dataclass-duck-typing, round-trip JSON serialization, and a regression test that MTG fields do NOT leak into `Receipt.sign()`'s canonical hash.

### Changed

- `Receipt.sign()` canonical payload is unchanged — hashes computed on 0.4.0 receipts remain valid after upgrade.
- Author field normalized to `Mousa Abumazin`.
- Status bumped to `Development Status :: 4 - Beta`.

### Design notes

- No hard dependency on the `mtg` package. The bridge coerces plain dicts OR dataclasses with a `to_dict()` method — so the `mtg` package stays optional.
- The bridge lives in ToolProof, not in `mtg` — ToolProof is the evidence layer, MTG is the primitive.

## 0.4.0 — earlier releases

See git history.
