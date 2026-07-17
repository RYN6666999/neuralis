# PSI Engine Evidence Ledger (DS-007A)

Forensic evidence for the "Rust PSI core at 2000Hz" claim and the PSI behavior
baseline. Every entry is graded. Grades:

- **E0** — Direct evidence: first-party source, binary, benchmark, or reproducible experiment.
- **E1** — Author claim: README / comment / commit message assertion with no measured proof.
- **E2** — Indirect evidence: launcher paths, protocol, filenames, state formats, fallback behavior.
- **I** — Inference: reasoned judgement from E0/E1/E2, with stated uncertainty.
- **D** — Neuralis design: our own additions (see roadmap); never disguised as author capability.

Rule applied throughout: an author README claim is **not** treated as established fact.
A Python fallback is **not** treated as the claimed Rust engine. Where the original
Rust PSI binary/source cannot be located, the entry says **cannot be verified**.

## Sources investigated

| Source | Ref / anchor |
|---|---|
| Author repo `lorryjovens-hub/laap-AGI` — branch `main` | `8393eb58f733419ade477c713beb52c0d970062b` |
| Author repo — branch `feat/port-old-modules` | `df111c732b029d3c1f6769bf2f96434bd22cebff` |
| Author repo — branch `feat/env-config-hermes` | `b055ac0161f7d001a59f8e03965f8c1403a3d890` |
| Author repo — PRs | `refs/pull/1/head` = b055ac0, `refs/pull/2/head` = 8393eb5 |
| PyPI `laap` (owner: lorryjovens per PyPI/libraries.io UI) | JSON API `https://pypi.org/pypi/laap/json`; versions 0.3.0, 0.3.1, 0.3.2 |
| Neuralis repo `RYN6666999/neuralis` | base `ab14499ec1d5f30e84b85c56e6c780c7eb4d6913` |
| crates.io / GitHub releases / tags | searched (see E0-11) |

Method: `git clone --mirror` of the author repo (all branches + PR refs), full-history
object scan (`git rev-list --all --objects`), and offline download + SHA256-verified
static extraction of all six PyPI artifacts (unzip / tar only — **no pip install, no
execution of any packaged code**).

---

## E0 — Direct evidence

### E0-1 — Author repo git history contains no Rust source, Cargo, or binary in any object
- **Grade:** E0
- **Claim:** Across all three branches and both PR refs, the entire git object set of
  `laap-AGI` contains **zero** `.rs`, `Cargo.toml`, `Cargo.lock`, `.exe`, `.dll`, `.so`,
  `.dylib`, `.wasm`, or `target/` paths.
- **Evidence:** `git rev-list --all --objects | awk '{print $2}' | sort -u` → 193 unique
  paths, none matching `\.rs$|cargo|\.exe|\.dll|\.so$|\.dylib|\.wasm|target/`.
- **Repo/branch:** laap-AGI / all refs.
- **Confidence:** High (exhaustive object scan of a mirror clone).
- **Limits / counter-evidence:** Absence in git history is not proof a private Rust core
  never existed; see E0-2 (binaries are structurally gitignored).

### E0-2 — `.gitignore` structurally excludes every compiled artifact
- **Grade:** E0
- **Claim:** The repo cannot commit a compiled PSI binary or a Rust build tree.
- **Original text:** `.gitignore` L21 `*.pyd`, L33 `target/`, L34 `*.exe`, L35 `*.dll`, L36 `*.so`.
- **Permalink:** https://github.com/lorryjovens-hub/laap-AGI/blob/8393eb58f733419ade477c713beb52c0d970062b/.gitignore#L33-L36
- **Confidence:** High.
- **Limits:** This *explains* the absence in E0-1 and means the public repo can neither
  confirm nor deny a private Rust binary. It is the key reason the verdict is C, not D.

### E0-3 — Author's own `psi_core/engine.py` is a self-labeled Python fallback (10 Hz), not Rust
- **Grade:** E0
- **Claim:** The only PSI engine implementation present in the author repo is pure Python,
  runs at a default `tick_ms=100.0` (10 Hz, floored at 10 ms = 100 Hz), and writes
  `latest.json` to disk on every tick.
- **Original text:** L2 `"LAAP PSI Core Engine — Python fallback."`; L37 `core_version: str = "python-1.0.0"`;
  L78 `tick_ms: float = 100.0`; L81 `self.tick_ms = max(10.0, float(tick_ms))`;
  L141 `def _write_state` → writes `latest.json` inside the per-tick `_run` loop.
- **Permalink:** https://github.com/lorryjovens-hub/laap-AGI/blob/df111c732b029d3c1f6769bf2f96434bd22cebff/psi_core/engine.py#L1-L82
- **Repo/branch:** laap-AGI / `feat/port-old-modules` only (absent on `main`).
- **Confidence:** High.
- **Limits:** This is the fallback, explicitly. It is not evidence about the claimed Rust core.

### E0-4 — PyPI `laap` ships a real PyO3 Rust extension `laap_core.pyd`, but it is NOT a PSI engine
- **Grade:** E0
- **Claim:** All three PyPI versions bundle `laap/laap_core.pyd`, a genuine compiled Rust
  extension (PyO3 0.21.2), **byte-identical** across versions
  (sha256 `531c83750b838a8712e0f8eee13015979aef98544505509172bfbdde9f83470e`, 484352 bytes).
  Its exported Rust types are `TokenCounter`, `KeywordSearch`, `MemoryEngine`,
  `ExperienceGraph`, `SessionManager`, `Sequence` — text/memory/session utilities.
  It contains **zero** PSI-physiology strings (`arousal`/`valence`/`prediction_error`/
  `2000hz`/`tick`/`need` count = 0).
- **Evidence:** `file` → `PE32+ executable (DLL) (GUI) x86-64, for MS Windows`;
  string dump shows `pyo3-0.21.2`, `parking_lot-0.12.5`, `hashbrown-0.16.1`, `rustc-demangle`,
  build path `<WINHOME>\.cargo\registry\src\index.crates.io\pyo3-0.21.2\...` and
  `<WINHOME>\.rustup\toolchains\stable-x86_64-pc-windows-msvc\...`; and the exported-symbol
  bundle `MemoryEngineExperienceGraphSessionManager` / `TokenCounterKeywordSearch`.
- **Artifact anchor:** `laap/laap_core.pyd` inside every wheel + sdist (see inventory below).
- **Confidence:** High.
- **Limits:** Proves the author has real Rust + PyO3 capability. Does **not** support the
  PSI 2000Hz claim — this binary is a different subsystem.

### E0-5 — PyPI `laap` Python PSI formulas (`cognition/needs.py`, `emotion.py`) — the real baseline, and Neuralis's true ancestor
- **Grade:** E0
- **Claim:** `laap/cognition/needs.py` is byte-identical across 0.3.0/0.3.1/0.3.2
  (sha256 `9f2eec33a32d1a517175312edb1f8fe550cbd3742631205501f39ed4baefab72`). It defines a
  Dörner 5-need system whose **fifth need is `ENERGY`** (not `GROWTH`), with
  `drive = max(0, target-current) * importance`, per-need `tick` decay toward 0 plus
  `np.random.normal(0, volatility*dt)`, `satisfy = min(1, current+amount)`, and
  `emotional_valence = 2*mean-1`. `emotion.py::EmotionGradient` smooths
  `valence → 2*avg-1` and `arousal → 0.3+0.7*drive` with `smoothing=0.3`.
- **Artifact anchor:** `laap-0.3.2.tar.gz` sha256 `58e128d0a187600d30abc44d7ef6fe05cbbd9887261b9e220f20182d2b85986d`, path `laap/cognition/needs.py`, `laap/cognition/emotion.py`.
- **Confidence:** High.
- **Limits:** The 5th need and several parameters differ from Neuralis (see behavior-spec contradiction table).

### E0-6 — PyPI build backend is plain setuptools; the `.pyd` is pre-compiled package data
- **Grade:** E0
- **Claim:** `pyproject.toml` build-backend = `setuptools.build_meta` (requires only
  `setuptools>=68`, `wheel`). No `setuptools-rust`, no `maturin`. `laap_core.pyd` is listed
  in `RECORD` and `SOURCES.txt` as ordinary package data — i.e. compiled elsewhere and
  bundled, with **no Rust source in the package**.
- **Artifact anchor:** `laap-0.3.2` `pyproject.toml`; `laap-0.3.2.dist-info/RECORD` line
  `laap/laap_core.pyd,sha256=UxyDdQuDiocS4Pju4TAVl5rvmFRFBVCRcr-93p-DRw4,484352`.
- **Confidence:** High.

### E0-7 — All six artifacts SHA256-verified against PyPI JSON
- **Grade:** E0
- **Claim/Evidence:** downloaded and hash-matched:

| Version | File | packagetype | py tag | size (bytes) | upload (UTC) | sha256 |
|---|---|---|---|---|---|---|
| 0.3.0 | laap-0.3.0-py3-none-any.whl | bdist_wheel | py3 | 573567 | 2026-06-10T14:59:22Z | 3c771bc6a9b7e74203af75f3f13efe439c567b823bc9bff04694cc87fb316173 |
| 0.3.0 | laap-0.3.0.tar.gz | sdist | source | 553593 | 2026-06-10T14:59:25Z | bdb200bfb0cb77a90fad25a19205011e9aeb0f1262116b7fde7b71cfdee9ee08 |
| 0.3.1 | laap-0.3.1-py3-none-any.whl | bdist_wheel | py3 | 794724 | 2026-06-10T16:02:10Z | f51aaf885342cdf82c2712e8d62d6a6d6b493a77377337b01124c86ac45106c7 |
| 0.3.1 | laap-0.3.1.tar.gz | sdist | source | 694739 | 2026-06-10T16:02:13Z | 2065f2e5fd6847556a1c5574d204b5721692098f24e71dc219cdaef578105c95 |
| 0.3.2 | laap-0.3.2-py3-none-any.whl | bdist_wheel | py3 | 794700 | 2026-06-10T16:05:26Z | aea2b30b5850ee6ddc29a12701e7006409dc396a2c6039d85289556b62b1fa29 |
| 0.3.2 | laap-0.3.2.tar.gz | sdist | source | 694692 | 2026-06-10T16:05:28Z | 58e128d0a187600d30abc44d7ef6fe05cbbd9887261b9e220f20182d2b85986d |

- **Download URLs:** `https://files.pythonhosted.org/packages/1b/26/.../laap-0.3.0-py3-none-any.whl`,
  `.../ba/f4/.../laap-0.3.0.tar.gz`, `.../a0/0f/.../laap-0.3.1-py3-none-any.whl`,
  `.../3c/e8/.../laap-0.3.1.tar.gz`, `.../ea/81/.../laap-0.3.2-py3-none-any.whl`,
  `.../e7/67/.../laap-0.3.2.tar.gz` (full paths in the PyPI per-version JSON).
- **Confidence:** High (all six matched; result `ALL_VERIFIED`).

### E0-8 — PyPI file inventory & version deltas
- **Grade:** E0
- **Claim:** 0.3.0 sdist = 242 files; 0.3.1 = 454; 0.3.2 = 454. The 0.3.1→0.3.2 source
  trees are identical (only version string changes; `cognition/needs.py` unchanged).
  0.3.0→0.3.1 is a large refactor (old `laap/api/`, `laap/cli/` trees replaced by
  `laap/agent_core/**` with `platforms/` and `plugins/`). The PSI cognition subsystem
  (`laap/cognition/{needs,emotion,goals,awareness}.py`, `laap/lifeform/physiology.py`,
  `laap/agent_core/psi_cognition.py`) is present in all versions; `laap_core.pyd` is
  present in all six artifacts.
- **Confidence:** High.

### E0-9 — PyPI `laap` contains no 2000Hz / 500μs / PSI benchmark anywhere
- **Grade:** E0
- **Claim:** No `2000Hz`, `500μs/500us`, or PSI tick-rate benchmark exists in the PyPI
  package. The only "heartbeat" references are `agent_core/lifeform.py` `heartbeat: float = 60.0  # bpm`
  (a simulated vital-sign metaphor) and a `protocol/laap_com.py` `HEARTBEAT = "heartbeat"`
  message-type enum. `cognition/needs.py::tick(dt)` has no bound rate and no daemon loop.
- **Artifact anchor:** `laap-0.3.2.tar.gz` (hash above).
- **Confidence:** High.

### E0-10 — Neuralis PsiCore self-declares descent from PyPI laap v0.3.2
- **Grade:** E0
- **Original text:** `laap/psi_core.py` L4 `基於 PyPI laap v0.3.2 的 needs.py + emotion.py 設計模式濃縮。`
  ("condensed from the design of PyPI laap v0.3.2's needs.py + emotion.py").
- **Permalink:** https://github.com/RYN6666999/neuralis/blob/ab14499ec1d5f30e84b85c56e6c780c7eb4d6913/laap/psi_core.py#L1-L8
- **Confidence:** High. Combined with E0-5, this fixes the lineage: Neuralis ← PyPI laap, **not** ← laap-AGI fallback.

### E0-11 — No public Rust PSI package or release
- **Grade:** E0 (negative)
- **Claim:** PyPI hosts only the three `laap` versions above (no `-psi` / `aris-psi` variants
  in this project). The author repo has **no** GitHub releases and **no** tags
  (`git tag` empty; `for-each-ref` shows only heads + PR refs).
- **Confidence:** Medium-High for what was checked. **Limits:** a crates.io / third-party
  mirror search is a lead only; per the quality gate, no third-party result is treated as a
  conclusion. No first-party Rust PSI crate/release was found.

---

## E1 — Author claims (README, unproven)

All from `laap-AGI` `main` README.md; none accompanied by source, binary, or benchmark.

### E1-1 — "Rust PSI core at 2000Hz"
- **Text (L67):** "Every heartbeat of the Rust PSI core at 2000Hz, every quantum reasoning
  pulse at 182 microseconds ..."
- **Permalink:** https://github.com/lorryjovens-hub/laap-AGI/blob/8393eb58f733419ade477c713beb52c0d970062b/README.md#L67
- **Limit:** Marketing/manifesto prose. No measurement.

### E1-2 — "Rust PSI Core (5 needs, 2000Hz) | 500 microseconds"
- **Text (L83):** performance table row. Also L104 ASCII diagram "Rust PSI Core (2000Hz)",
  L146 "2000Hz physiological heartbeat", L359 "PSI core heartbeat | 500 microseconds (Rust)",
  L372 "PSI Heartbeat | 100ms | Rust-native cognitive rhythm".
- **Permalink:** https://github.com/lorryjovens-hub/laap-AGI/blob/8393eb58f733419ade477c713beb52c0d970062b/README.md#L83
- **Limit:** Internally inconsistent — the same README also states a 100 ms heartbeat (L372),
  which is 10 Hz, contradicting 2000 Hz.

### E1-3 — "psi_core/ # Rust source (2000Hz PSI)" + "Cargo.toml"
- **Text (L328, L330):** repo-tree diagram claims a `psi_core/` Rust source directory and a `Cargo.toml`.
- **Permalink:** https://github.com/lorryjovens-hub/laap-AGI/blob/8393eb58f733419ade477c713beb52c0d970062b/README.md#L328-L330
- **Limit:** Directly contradicted by E0-1/E0-3: `psi_core/` is absent on `main` and is
  Python-only (`engine.py`, `runner.py`, `__init__.py`) on `feat/port-old-modules`; no
  `Cargo.toml` exists in any object.

---

## E2 — Indirect evidence

### E2-1 — Launcher references a Cargo-release `.exe`, guarded by `.exists()`
- **Text:** `aris_brain/laap_integrator.py` L883 `rust_bin = BRAIN / "psi_core" / "target" / "release" / "aris_psi_core.exe"`; L884 `if rust_bin.exists():` then `subprocess.Popen([...])`.
- **Permalink:** https://github.com/lorryjovens-hub/laap-AGI/blob/8393eb58f733419ade477c713beb52c0d970062b/aris_brain/laap_integrator.py#L879-L899
- **Reading:** The path follows the Cargo `target/release/` convention, and the launcher
  degrades gracefully when the binary is absent. Consistent with *either* a real private
  Rust build *or* an aspirational reference; cannot distinguish from public evidence.

### E2-2 — Integration launcher: Rust-if-exists-else-Python, Windows-only spawn flag
- **Text:** `laap_brain/psi_core_integration.py` L39 `PSI_CORE_BINARY = BRAIN_DIR / "psi_jspace_bridge" / "aris_psi_core.exe"`;
  L66 `if self.binary.exists(): return True`; L128 `if self.binary.exists(): return self._start_rust()`;
  L131 `"Rust PSI Core binary not found; trying Python fallback"`; `_start_rust` uses
  `subprocess.CREATE_NO_WINDOW` (a Windows-only flag).
- **Permalink:** https://github.com/lorryjovens-hub/laap-AGI/blob/df111c732b029d3c1f6769bf2f96434bd22cebff/laap_brain/psi_core_integration.py#L38-L131
- **Reading:** The intended Rust artifact was a Windows `.exe`; on any clean checkout the
  `.exists()` check is False (binary gitignored, E0-2) → always the Python fallback.

### E2-3 — `psi_embedding.py` probes for the `.exe` via Windows `tasklist`
- **Text:** `aris_brain/psi_semiotics/psi_embedding.py` L205/L218/L223 reference
  `aris_psi_core.exe` and `['tasklist', '/FI', 'IMAGENAME eq aris_psi_core.exe', ...]`.
- **Permalink:** https://github.com/lorryjovens-hub/laap-AGI/blob/8393eb58f733419ade477c713beb52c0d970062b/aris_brain/psi_semiotics/psi_embedding.py#L205-L226
- **Reading:** Another consumer expecting a running Windows `.exe`; still only a reference.

### E2-4 — `laap/rust_bridge.py` is an explicit Python stub, and not PSI
- **Text:** docstring "Rust 核心桥接 stub ... 优雅降级"; `_StubBridge.__bool__` returns `False`;
  methods `scan_complexity` / `scan_threats` (code analysis, not PSI).
- **Permalink:** https://github.com/lorryjovens-hub/laap-AGI/blob/df111c732b029d3c1f6769bf2f96434bd22cebff/laap/rust_bridge.py#L1-L52
- **Reading:** Where the repo says "Rust", the shipped code resolves to a Python no-op stub.

### E2-5 — File-based tick protocol with per-tick disk write
- **Text:** `psi_core/engine.py` — reads `input_queue.json`, watches `daemon.stop`, writes
  `latest.json` inside the loop; `psi_core_integration.py` docstring L11-L16 documents the
  same protocol ("PSI 引擎每 tick 写入 state/latest.json").
- **Permalink:** https://github.com/lorryjovens-hub/laap-AGI/blob/df111c732b029d3c1f6769bf2f96434bd22cebff/psi_core/engine.py#L242-L262
- **Reading:** The documented protocol performs a JSON disk write **every tick**. See I-3.

### E2-6 — The commit that added the Python fallback describes "honest cleanup"
- **Text:** commit `6e5a03f3927640cd17fc6cd70fdbab8414cc216d` — author `Ao (PSI Refactor) <ao@laap.ai>`,
  2026-07-15 — message "fix: honest first-stage cleanup + Python PSI Core fallback ... Add
  Python PSI Core fallback (psi_core/) so the engine runs without Rust binary".
- **Permalink:** https://github.com/lorryjovens-hub/laap-AGI/commit/6e5a03f3927640cd17fc6cd70fdbab8414cc216d
- **Reading:** The author themselves frames the Python engine as a fallback added so the
  system "runs without Rust binary" — i.e. the Rust binary was, at that point, not present.

---

## I — Inferences

- **I-1:** The author demonstrably has real Rust+PyO3 capability (E0-4), but the only public
  Rust artifact implements token/memory/session utilities, not PSI. Confidence: High.
- **I-2:** The "2000Hz Rust PSI core" exists in public form **only** as README claims (E1) and
  launcher path references (E2). No public Rust PSI source, Cargo, binary, release, or
  benchmark was found. Whether a private Rust PSI `.exe` ever existed **cannot be verified**
  (E0-2 hides it structurally). Confidence: High that it is unverified; deliberately not
  claiming it never existed.
- **I-3:** The documented protocol writes `latest.json` every tick (E2-5). At 2000 Hz that is
  2000 JSON serializations + disk writes per second. The README describes no snapshot/hot-loop
  decoupling. So "2000Hz *with* per-tick `latest.json`" is internally implausible on a normal
  OS; a real 2000Hz core would have to move I/O out of the hot path — which the public
  material never describes. Confidence: Medium-High.
- **I-4:** Neuralis PsiCore descends from PyPI `laap` (E0-5, E0-10), not from the laap-AGI
  Python fallback (different 5th need, decay target, and dominance rule). Confidence: High.

---

## D — Neuralis design

Neuralis's own engineering (v2 design, borrowing decisions, and the Rust engine) is **D** and
is never attributed to the author. It lives outside this ledger:

- `docs/rust-psi/2000hz-verdict.md` — the verdict on the author's claim, and the explicit
  separation between the author's claim and Neuralis's own measured result.
- `docs/rust-psi/borrowing-matrix.md`, `docs/rust-psi/neuralis-psi-v2-minimal-spec.md`,
  `docs/rust-psi/2000hz-runtime-spec.md` — v2 design and borrowing analysis
  (branch `task-007b-psi-borrowing-analysis`; not on `main` at this ledger's base).
- `rust/psi-engine/**` — the Neuralis Rust implementation and its benchmark
  (branch `task-008-rust-psi-engine`; not on `main` at this ledger's base).

**Boundary rule:** Neuralis reaching 2000 Hz with its own Rust engine is a Neuralis (D)
result measured by Neuralis (E0). It is **not** retroactive proof of the author's claim.
The two must never be conflated. See `2000hz-verdict.md` §"What our own engine does and
does not prove".

---

## Cannot be known from public information

- Whether a private Rust PSI core (`aris_psi_core.exe`) ever existed, its formulas, or any
  real tick-rate it achieved.
- Any measured PSI tick rate, latency distribution, or deadline behavior for a Rust PSI core.
- The provenance relationship (if any) between the PyPI `laap_core.pyd` Rust module and the
  claimed Rust PSI core — they share a repo name but the `.pyd` is not PSI.
- Whether the PyPI `laap` project and `laap-AGI` share an engine: **same author is
  supportable; same PSI engine is not** — their PSI code differs (E0-5 vs E0-3), and licenses
  differ (PyPI MIT vs laap-AGI Apache-2.0).
