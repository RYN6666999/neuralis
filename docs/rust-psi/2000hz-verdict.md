# 2000Hz Verdict — the "Rust PSI core at 2000Hz" claim

**Scope:** this document judges **one** thing — the assertion that a Rust PSI core runs at
2000Hz / 500µs. Evidence is in `docs/rust-psi/evidence-ledger.md`. Grades: E0 direct,
E1 author claim, E2 indirect, I inference, D Neuralis design.

> **Read this first — the author already retracted the headline claim.**
> "2000Hz / Rust PSI Core" appears only on `main`, which is **not** the repo's default branch
> and is 3 days older than it. On the **default** branch (`feat/port-old-modules`, what any
> visitor or `git clone` actually gets) the `2000Hz|Rust PSI` count is **0**; the author
> relabelled it 「Python fallback；Rust binary optional」, 「~100 ms」, and 「Rust 原生 PSI 核心
> …… 属于可选扩展或后续阶段」 (E0-12). Their own commit called it an "honest cleanup", and the
> content matches the message. This document judges the **residual** claim that survives on
> the default branch — not the superseded copy on `main`.

---

## Verdict

# C — CLAIMED, NOT VERIFIED

**What is being judged:** the residual assertion on the default branch (README L515) that the
native Rust core 「可达 500 μs」 ("can reach 500µs" = 2000Hz) as an *optional external binary*,
while the stated actual heartbeat is ~100 ms.

That residual assertion carries no source, no `Cargo.toml` for a PSI crate, no compiled PSI
binary, no release, and no benchmark in any first-party public artifact (E0-1, E0-11). It
survives only as prose (E1) plus launcher path references (E2). A real first-party Rust
binary **does** exist — and it is not a PSI engine (E0-4).

**The superseded `main` copy** (2000Hz headline, "psi_core/ # Rust source", "Cargo.toml")
would receive the same letter on the same evidence — but it is no longer the author's
position and must not be quoted as if it were.

## Why C and not the others

| Option | Rejected because |
|---|---|
| **A — VERIFIED** | Requires Rust source/binary **plus** a reproducible benchmark. Neither exists for the PSI core. Full-history object scan of all three branches + both PR refs found zero `.rs`, `Cargo.toml`, `Cargo.lock`, `.exe`, `.dll`, `.so`, `target/` paths (E0-1). No tags, no GitHub releases (E0-11). |
| **B — PARTIALLY VERIFIED** | Requires implementation evidence for the PSI core. There is none — only a path string the launcher tests with `.exists()` (E2-1, E2-2). The only shipped PSI *implementation* is Python (E0-3). A path reference is not an implementation. |
| **D — CONTRADICTED** | Would require direct evidence that a Rust PSI core is impossible or provably absent. Not available: `.gitignore` excludes `*.exe`, `*.dll`, `*.so`, `*.pyd`, `target/` (E0-2), so a private Windows build is *structurally invisible* to the public repo. Absence of evidence is not disproof. |
| **E — UNKNOWN** | Would require that even the claim's source be unidentifiable. It is fully identified (README `main` L67/L83/L104/L146/L328-330/L359/L372), and the public artifacts are exhaustively characterized. We know precisely what does and does not exist publicly. |

## Where the "2000Hz" number comes from

Single first-party origin: the `laap-AGI` README on the **older, non-default** `main` branch
(`8393eb58f733419ade477c713beb52c0d970062b`, 2026-07-12) — **superseded** on the default
branch 3 days later (E0-12).

- L67 — "Every heartbeat of the Rust PSI core at 2000Hz" (manifesto prose)
- L83 — table: "Rust PSI Core (5 needs, 2000Hz) | 500 microseconds"
- L104 — ASCII diagram: "Rust PSI Core (2000Hz)"
- L146 — "2000Hz physiological heartbeat"
- L328-330 — repo tree claiming `psi_core/  # Rust source (2000Hz PSI)` and `Cargo.toml`
- L359 — "PSI core heartbeat | 500 microseconds (Rust)"

No measurement, timing harness, or tick statistic accompanies any of them. There is no
benchmark file anywhere in the repo or in the PyPI package (E0-9).

## What "2000Hz" is supposed to mean — unspecified, and self-contradicted

The claim never states whether 2000Hz denotes internal state update rate, `latest.json` write
rate, IPC rate, or marketing shorthand. The public material makes it **internally
inconsistent** two different ways:

1. **README vs README.** On `main`, L83/L104/L146 say 2000Hz (500µs) while L372 of the *same*
   README says "PSI Heartbeat | 100ms | Rust-native cognitive rhythm" — 10 Hz. Both describe
   the same component. They differ by 200×. The author resolved this on the default branch in
   favour of the slower figure: 「PSI 核心心跳 | ~100 ms | Python fallback」 (E0-12).
2. **Claim vs documented protocol.** The only documented PSI protocol writes `latest.json`
   on **every tick** (E2-5; `psi_core/engine.py` `_write_state` inside the loop, and
   `psi_core_integration.py` "PSI 引擎每 tick 写入 state/latest.json"). At 2000Hz that is
   2000 JSON serializations + file writes per second. The public material describes no
   snapshot/hot-loop decoupling. So "2000Hz *with* per-tick `latest.json`" is not plausible
   on a normal OS (I-3). A real 2000Hz core would have to move I/O off the hot path — which
   nothing in the public material describes.

**Answer to "internal update / JSON write / IPC / marketing?":** unspecified by the author, and
under the only protocol the author documents, the three technical readings are mutually
inconsistent. On public evidence the claim functions as prose, not a specification.

## The Rust that does exist — and why it is not this claim

PyPI `laap` 0.3.0/0.3.1/0.3.2 each bundle `laap/laap_core.pyd`: a genuine compiled Rust
extension built with PyO3 0.21.2, PE32+ x86-64 Windows DLL, byte-identical across all three
versions (sha256 `531c83750b838a8712e0f8eee13015979aef98544505509172bfbdde9f83470e`, E0-4).

It is real Rust. It is **not** a PSI engine:

- Exported Rust types: `TokenCounter`, `KeywordSearch`, `MemoryEngine`, `ExperienceGraph`,
  `SessionManager`, `Sequence` — text/memory/session utilities.
- PSI-physiology string count inside the binary (`arousal`, `valence`, `prediction_error`,
  `physiolog`, `2000hz`): **0**.
- Build backend is plain `setuptools.build_meta` — no `maturin`, no `setuptools-rust`. The
  `.pyd` is pre-compiled package data; no Rust source ships in the package (E0-6).

So: the author demonstrably has real Rust + PyO3 capability (I-1). That capability was
applied to a different subsystem. It does not support the PSI 2000Hz claim, and it must not
be cited as if it did.

## What our own engine does and does not prove

Neuralis's Rust `PsiEngine` v2 (branch `task-008-rust-psi-engine`, not on `main` at this
document's base `ab14499`) reports a measured sustained 2000.0 ticks/s with 0.0000% deadline
miss, p99 compute 3-11µs, peak 35-66µs, and 0µs drift, plus bit-identical deterministic
replay under a fixed seed.

- **This is D + E0:** a Neuralis design, measured by a Neuralis benchmark we can rerun.
- **This is not evidence about the author.** It shows *a* Rust PSI core can hit 2000Hz on
  specific hardware under a specification we wrote. It says nothing about whether the
  author's `aris_psi_core.exe` ever existed or what rate it reached.
- **The verdict above is unchanged by it.** Our result does not upgrade the author's claim
  from C. Conflating "we achieved 2000Hz" with "the author's 2000Hz is verified" would be
  exactly the substitution this forensics exists to prevent.

One transferable finding, however, corroborates I-3 empirically: our engine only sustains the
rate because snapshot publishing is decoupled from the hot loop (100Hz publish vs 2000Hz
tick) and it does **no** JSON/disk I/O per tick. An engine that writes `latest.json` every
tick — the only protocol the author documents — is doing the one thing our measurements say
you cannot do at this rate.

## Honest acceptance definition (D)

Marked **D** — Neuralis's own standard, not the author's. Specified in
`docs/rust-psi/2000hz-runtime-spec.md` and enforced by `psi-bench` (both on branches not yet
on `main`). Summarized here so this verdict stands alone:

- Target period 500µs; sustained rate ≥ 2000 tick/s.
- Report mean, p50, p95, p99, max, deadline-miss count, drift, CPU, memory — never a mean alone.
- Durations: 60s smoke, 10min sustained; longer soak deferred.
- No JSON/disk I/O on the hot path; snapshot/logging downsampled and off the hot loop.
- Fixed seed ⇒ deterministic replay.
- **No hard-real-time claim on a non-real-time OS.** Best-effort scheduling with a measured
  deadline-miss ratio is what we assert; a guarantee is not.

## Cannot be known

- Whether `aris_psi_core.exe` ever existed, its formulas, or any rate it achieved.
- Any measured tick rate, latency distribution, or deadline behavior for an author PSI core.
- Whether the PyPI `laap_core.pyd` Rust module shares provenance with the claimed Rust PSI
  core. They share a project name; the `.pyd` is not PSI.

## Standing correction for downstream docs

Do not write "LAAP has a Rust PSI core at 2000Hz". Also do not write "the author claims a
2000Hz Rust PSI core" in the present tense — on their default branch, they no longer do. On
public evidence the accurate statements are:

1. A 2000Hz Rust PSI core was claimed on the **older, non-default `main`** branch and was
   **retracted** on the default branch, which now says "Python fallback; Rust binary optional"
   and ~100 ms (E0-12).
2. What survives on the default branch is a weaker, unverified assertion that an *optional
   external* Rust binary 「可达 500 μs」 — verdict C.
3. The author's only public PSI **implementation** is Python, default 100ms tick (10Hz),
   writing `latest.json` every tick (E0-3).
4. The author's only public Rust **artifact** is a PyO3 module for token/memory/session
   utilities, not PSI (E0-4).
5. Neuralis's own Rust engine independently reaches a measured 2000Hz (D, E0) — a separate
   fact that proves nothing about (1) or (2).
