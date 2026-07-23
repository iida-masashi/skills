# Exit Codes

| Code | Meaning | When |
|------|---------|------|
| `0` | Pass | All checks succeeded. |
| `1` | Policy / test violation | Ruff, AST policy, MyPy, or pytest failed; or `psc baseline diff` found new violations. **Red CI.** |
| `2` | Internal error | Unexpected exception inside `psc` (rare; bug in the gate itself). **Red CI; investigate.** |
| `3` | Configuration error | Missing `pyproject.toml`, malformed baseline JSON, missing `[heal]` extras when `psc heal` was invoked. **Red CI; the workflow setup is wrong.** |

`psc` deliberately distinguishes 1, 2, and 3 so a CI alert routing rule can
differentiate "developer needs to fix code" (1), "infra broke" (2), and "the
pipeline itself is misconfigured" (3).

## Backwards-compatibility

The contract above is stable. Adding a new code in the future would happen at
`4+`; existing codes will not be repurposed.
