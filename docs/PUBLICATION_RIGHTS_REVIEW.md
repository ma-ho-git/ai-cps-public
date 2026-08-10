# Publication Rights Review

This document is the release gate for publishing `ma-ho-git/ai-cps-runtime`.
The machine-readable state is stored in `configs/publication_rights.json`.

## Required Confirmations

- [x] Grum AI-CPS origin is published under AGPL-3.0 and is attributed in
  `THIRD_PARTY_NOTICES.md`.
- [x] All project contributors have confirmed public distribution of their
  contributions under `AGPL-3.0-only`.
- [x] The five active training datasets are owned by the project or approved
  for public redistribution.
- [x] The three current model artifacts may be redistributed and their
  training data are cleared.
- [x] The three runtime traces contain no confidential plant data and may be
  published.
- [x] Current UML assets are project-generated; no full third-party paper is
  part of the runtime tree.
- [x] A final tracked-tree scan confirms that `.env`, reports, credentials,
  development notebooks and historical research artifacts are absent.

The project owner confirmed the four release-specific rights decisions on
2026-08-10. Detailed personal or contractual evidence is retained outside
Git; this repository records only the non-confidential release decision.

## Recording Approval

For every completed item, retain the confirmation outside Git if it contains
personal or contractual information. Change only the corresponding `status`
in `configs/publication_rights.json` from `pending` to `approved` and summarize
the non-confidential basis here.

The tag workflow must run:

```bash
python3 tools/check_public_release_readiness.py --require-approved
```

The public repository and release tag must not be created while this command
reports pending or rejected rights.
