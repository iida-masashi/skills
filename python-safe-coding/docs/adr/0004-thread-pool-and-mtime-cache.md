# ADR 0004 — ThreadPool + mtime/size cache for AST checker

- **Status**: Accepted (2026-04-28)
- **Deciders**: python-safe-coding maintainers

## Context

`psc ast` is invoked on every commit through pre-commit hooks. As consumer
repositories grow into hundreds of `.py` files, the single-threaded scan
becomes the dominant cost of the gate, and most files have not changed since
the last run.

We need a parallel walk and a per-file result cache, but we also need to
avoid the failure modes that *both* features classically introduce.

## Decision

### Parallelism: ThreadPoolExecutor, not ProcessPool

`ast.parse` is a C call that releases the GIL, so threads scale fine for this
workload. ProcessPool's spawn cost on Windows (the primary dev environment)
exceeds the parallel gain for typical codebases (<100 files).

Parallel kicks in only when `len(files) >= 16`. Below that, pool spin-up is
pure overhead. Default worker count is `min(cpu_count, 8)`.

### Output ordering: sorted by path

`pool.map` preserves submission order on its own, but to make the contract
explicit and to survive future changes (e.g. switching to `as_completed`),
`check_target` sorts by path before returning. Reproducible output matters
for CI diffs and for users grepping log files.

### Cache key: (path, mtime_ns, size, _CHECKER_VERSION)

Mirrors what `make`/`ninja` use. Hashing every file's content on every run
defeats the purpose of caching.

`_CHECKER_VERSION` is a constant inside `ast_checker.py`. It must be bumped
whenever a rule is added or modified — otherwise, on the next run, every
file's cached "clean" verdict is silently reused under the new rule, and CI
goes green on broken code. This is the failure mode the `_CHECKER_VERSION`
field exists to prevent.

### Cache is opt-in (`--cache-dir`)

Cache problems are notoriously hard to debug ("why isn't psc seeing my
fix?"). Default-off keeps `psc ast` predictable; opt-in lets pre-commit and
CI configurations enable it explicitly with one flag. Same shape as
`--baseline`.

### Cache failures never fail a check

`store(...)` swallows `OSError` (disk full, permission denied) silently. The
check itself runs whether or not the cache write succeeds.

### Scope: AST checker only

Caching `psc gate` would mean caching the AST step alone (Ruff, MyPy, pytest
already run as separate subprocesses with their own caching). The complexity
of plumbing partial cache state through the gate runner is not justified by
the millisecond savings on the AST step alone. `psc ast` and `psc baseline`
are what pre-commit hammers — they get the cache.

## Consequences

### Positive
- Near-zero cost on incremental runs of large repos.
- Cache invalidates automatically on edits and on rule changes.
- Output remains deterministic regardless of thread scheduling.
- Cache directory is opaque; consumers can `rm -rf .psc-cache` safely.

### Negative
- Forgetting to bump `_CHECKER_VERSION` is a silent failure mode. We rely on
  code review to catch this. (A pre-commit hook that fails on changes to
  `ast_checker.py` without a version bump is on the table for ADR 0005.)
- ThreadPool gains diminish at high file counts because of GIL contention on
  non-AST work (path resolution, dict ops). For our workload (file walk +
  AST parse), measurements show acceptable scaling up to ~8 threads.

## Alternatives considered

1. **ProcessPool** — rejected; spawn cost > parallel gain on Windows for
   small/medium repos, and the workload is GIL-friendly.
2. **Content-hash cache key** — rejected; hashing every file every run
   negates the benefit. mtime+size is the standard build-system trade-off.
3. **Default cache=on** — rejected; "why isn't psc seeing my fix" support
   debt outweighs the convenience.
4. **Cache `psc gate`** — deferred; the AST step is a small fraction of
   `gate`'s runtime, and Ruff/MyPy/pytest already cache themselves.
