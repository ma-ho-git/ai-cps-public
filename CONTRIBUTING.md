# Contributing

Contributions are welcome through issues and pull requests in
`ma-ho-git/ai-cps-runtime`.

## Before Changing Code

1. Read `AGENTS.md` and `docs/AI_DEVELOPMENT_HANDOVER.md`.
2. Keep MQTT topics, payloads, QoS, feature order, model classes and semaphore
   behavior unchanged unless the change explicitly migrates that contract.
3. Do not commit `.env`, credentials, reports, Docker volumes, local model
   candidates or raw research artifacts.
4. Add tests and update the relevant source-of-truth documentation.

## Licensing And Provenance

By contributing, you confirm that you have the right to submit the work under
`AGPL-3.0-only`. Preserve existing copyright, license and attribution notices.
Identify copied or adapted third-party material in the pull request and add the
required notice before it is merged.

Commits should include a Developer Certificate of Origin sign-off:

```bash
git commit --signoff
```

The sign-off certifies the Developer Certificate of Origin 1.1:
<https://developercertificate.org/>.

## Minimum Validation

- Python: relevant unit tests and `py_compile`
- Node-RED/MQTT: JavaScript tests, Flow export and Compose validation
- Runtime behavior: standard trace and affected guard profiles
- Documentation: links, paths and `git diff --check`

Pull requests must describe the behavioral effect, validation evidence,
scientific implications and any remaining risk.
