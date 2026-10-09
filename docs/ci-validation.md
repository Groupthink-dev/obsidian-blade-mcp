# CI documentation fast path

The versioned classifier compares the complete PR against its fetched target merge base, or a push against its previous successful same-branch push. Missing or untrusted history, manual runs, empty diffs, unknown paths and mixed changes require full validation. Renames classify both sides.

Only README.md, CHANGELOG.md and Markdown directly under docs/ or docs/adr/ qualify. Runtime SKILL.md and all code, fixtures, packaging and CI configuration remain full validation. The docs step checks tracked Markdown and runs eleven classifier regressions before the existing validate step can skip dependency installation. Existing status names, runner routing and three-push/three-PR protection gates are unchanged.
