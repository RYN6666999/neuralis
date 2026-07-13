# 作者「量子引擎」描述彙整（開發規格）

從 `laap-AGI` 原始碼 + 論文（`references/Harness-Consciousness-Engineering.md`）抓出的
所有關於「量子引擎」的描述，彙整成可開發的規格。**忠實萃取，不加料**；我的補充判斷會標「按此推斷」。

> 先破一個誤解：**「量子」是比喻，不是量子計算/量子位元。** 全部證據都指向高維向量幾何：
> QRE 是「512D 向量引擎」、V12.1 是「16384D 語義空間」、Ψ-Semiotics 是 Clifford 幾何代數。
> 沒有任何一處需要量子硬體。你要的是 SIMD/線性代數，不是 qubit。

---

## 0. 關鍵區分：作者有「兩個」被叫做量子的引擎，是不同東西

| | **PSI Core（生理層）** | **QRE / QuantumVM（推理層）** |
|---|---|---|
| 論文定位 | 生理層 · 5 需求維度 · 2000Hz 心跳 | QRE 量子推理 · 512D · 182μs |
| 語言 | **Rust**（~2000 行） | Python（~1500 行）/ V12.1 語義核 16384D（~2500 行） |
| 狀態 | Python 參考實作**存在**（`psi_bridge.py`）；Rust 版=`psi_core`（缺） | `psilang_v2` **缺**（agi_kernel 載入失敗）；`psilang_hott.py` 部分存在 |
| 做什麼 | 需求振盪 → 情緒/注意力 → 寫 `state/latest.json` | 幾何符號推理：概念=向量、類比=旋轉、符號組合 |
| 對應 stub | LAAP 的 cognitive_state 來源 | agi_kernel（被 `and False` 停用） |

**你之前想用 Rust 寫的、我建議的目標 = PSI Core（左欄）。** 若你要的是「符號推理」那顆 = QRE（右欄）。
下面兩個都給規格。

---

## 1. PSI Core（Rust 2000Hz 生理引擎）

### 論文原文
- 「生理層 · PSI Core (Rust)：5 需求維度 · 2000Hz 心跳 · 注意力選擇 · 情緒梯度」
- 性能：「PSI 生理心跳 (Rust) **500μs**」（即 2000Hz）
- 未來：「硬體加速：PSI 引擎的 FPGA 實現 (2000Hz → 20kHz)」

### 執行合約（`psi_core_bridge.py` 寫死）
- `psi_core` 每 **500μs** 寫入 `state/latest.json`
- Python 端輪詢該檔 → 發布到 CognitiveBus
- **輸出 schema**（bridge 讀的 key）：
```json
{
  "needs": {"competence":0.5,"autonomy":0.5,"relatedness":0.5,"certainty":0.5,"growth":0.5},
  "emotion": "neutral",          // positive_high|positive_mild|neutral|negative_mild|negative_high|curious|confused
  "arousal": 0.5, "dominance": 0.5,
  "attention_focus": "idle",     // user|task|self|environment|memory|planning|learning|idle
  "attention_intensity": 0.5,
  "quantum_engine": "none", "quantum_response": "",
  "psi_cycle": 0, "timestamp": 0.0,
  "self_presence": 0.5, "curiosity": 0.3
}
```

### 演算法（可從 `psi_jspace_bridge/psi_bridge.py` 直接移植，0-dep numpy 參考實作）
`PsiBridge.run_cognitive_cycle()` 一輪 =：
1. `_decay_energy()` — 能量隨時間衰減
2. `_drift_needs()` — 每個需求向 0.5 回歸：`need += (0.5 - need) * 0.05`
3. `_update_needs_from_input(text, hints)` — 關鍵詞 → 需求偏移，clamp [0.1, 0.9]
4. `_update_attention(text)` — 由 dominant_need 推 attention_focus
5. `_compute_affect(hints)` — 5 需求 (c,a,r,cert,g) → valence/arousal
6. `generate_prompt_preamble()` — 產生注入 prompt 的字串
- 需求名：`NEED_NAMES = [competence, autonomy, relatedness, certainty, growth]`
- 狀態持久化：`psi_state.json`（跨回合）

**按此推斷：** Rust 版就是把上面 6 步寫成一個 500μs tick 的 loop，每 tick 更新結構、
序列化寫 `state/latest.json`（原子寫：先寫 tmp 再 rename）。5 個 f32 + 幾個純量，
零外部依賴，`serde_json` 就夠。這是真正 latency-critical 且 Python 做不好的地方。

---

## 2. QRE / QuantumVM / Ψ-Semiotics（幾何符號推理引擎）

這是 `agi_kernel.py` 需要但缺的 `psilang_v2`。完整形式化規格在
`aris_brain/psi_semiotics/psi_semiotics_spec.md`（Ψ-Semiotics v1.0）。

### 核心思想（符號=語義空間中的幾何區域）
- 語義空間 `S = ℝ¹⁶³⁸⁴`（或 ℝ¹⁰²⁴ / QRE 用 512D）
- 符號 `σ = (c, r, M, {T_α})`：中心向量 c、語義半徑 r、multivector M、模態變換集
- 符號場 `Φ_σ(v) = exp(-d(v,c)²/2r²)`（高斯）
- 符號激活 `σ* = argmax_σ Σ_i w_i·Φ_σ(E_i(x_i))`

### 幾何代數（Clifford Cl(n)）— 這是引擎的數學核
- 概念 = multivector：`α₀ + α₁e₁ + α₂e₁₂ + α₃e₁₂₃ + ...`
- 幾何積：內積 `a·b=(ab+ba)/2`（語義相似）、外積 `a∧b=(ab-ba)/2`（語義關係）
- **類比 = 旋轉（rotor）**：`R=exp(-B/2)`，`v'=R·v·R†`
  - `a:b :: c:?` → 找 R 使 `R·c_a·R†≈c_b`，再 `v_?=R·c_c·R†`
  - 作者聲稱：一個 rotor 乘法 O(n²) vs Transformer O(n²·d)，「快幾個數量級」
- 符號組合 4 種：加法 `⊕`（歸一化和）、乘積 `⊗`（元素積）、關係 `→`（變換 T）、否定 `¬`（-c）
- 符號漂移：`c_σ ← c_σ + η(v_context - c_σ)`

### PsiLang 語言（`agi_kernel.py` 實際用的語法）
QuantumVM 執行 PsiLang。管線：`Compiler().compile(Parser(Lexer(src).tokenize()).parse())` → instrs
啟動載入 `core_identity.psi / core_psi.psi / core_language.psi`。語法範例（agi_kernel pulse）：
```
qstate pulse_1 = |cycle⟩ * 0.5
concept cycle_1 { valence: 0.5, tags: ["agi_pulse"] }
cycle cogn_1 {
    perceive |pulse⟩ * 0.3
    select relatedness = 0.7
    integrate temperature = 0.4
}
```
- `qstate NAME = |ket⟩ * scale` — 量子態（ket 記法）
- `concept NAME { valence:, tags:[] }` — 概念定義
- `cycle NAME { perceive / select / integrate }` — 認知循環三步

### QuantumVM 介面合約（agi_kernel 呼叫的表面）
```python
vm = QuantumVM(dim=16384)          # 或 512 / 1024
vm.load_program(instrs)
result = vm.run(max_steps=2000)    # -> {"steps": int}
vm.get_entropy()                   # -> float
vm.concept_network                 # 概念集合（len 可取）
vm.associative_memory              # 聯想記憶（len 可取）
```
optional `agi_memory` 模組：`load_vm / save_vm / decay / get_stats`

### 已存在的參考實作（別從零開始）
- `psi_semiotics/psilang_hott.py` — PsiLang v3 的 HoTT 型別系統（Rotor=Path、類比=2-Path、符號漂移=Path deformation、元認知=型別檢查）。numpy，可跑。
- `psi_semiotics/psi_semiotics_core.py` / `structured_encoder.py` / `math_physics_lib.py` / `semantic_dict.py` — 幾何代數與編碼器組件
- `quantum_bridge.py` → `quantum_psi.py`（`QuantumPSI, NeedVector, QPSIN_Bridge`）：perceive→select→integrate；QuantumMemory：糾纏共鳴→退相干→夢境鞏固；PSI-N 五層排程（微/中/宏/元/超）

### 作者給的實作路線圖（psi_semiotics_spec.md §8，~1750 行 Python）
1. 符號庫資料結構 + 語義場計算（~200）
2. 幾何代數 multivector 操作（~300）
3. 類比推理轉子搜尋（~200）
4. 多模態符號三角測量（~200）
5. 符號組合 ⊕⊗→¬（~200）
6. PsiLang v3 編譯到幾何操作（~300）
7. 符號漂移追蹤與演化（~150）
8. 與現有推理引擎整合（~200）

---

## 3. 建議的開發順序（判斷，非萃取）

**先做 PSI Core（§1），別先碰 QRE（§2）。** 理由：
1. PSI Core 有能跑的 Python 參考（`psi_bridge.py`），Rust 化 = 忠實移植 6 步 loop，範圍小、可測（拿 Python 輸出當 golden）。
2. 它接的 seam（`state/latest.json`）已驗證存在，drop-in 零改 Python。
3. QRE/Ψ-Semiotics 是 ~1750 行的研究級工程（Clifford 代數 + rotor 搜尋 + 語言編譯器），
   而且它的「快幾個數量級」「類比 = 旋轉」是**未經獨立驗證的作者聲稱**——先讓 PSI Core 把
   底座跑穩，再投 QRE。

**反悔條件：** 如果你要的「量子引擎」明確就是「符號推理/類比」那顆（不是生理心跳），
那 §2 才是目標，起點是移植 `psilang_hott.py` + 照 §8 路線圖，不是寫 Rust 心跳。

---

## 來源檔案
- `aris_brain/psi_semiotics/psi_semiotics_spec.md`（Ψ-Semiotics 完整形式化）
- `aris_brain/psi_core_bridge.py`（2000Hz 合約 + state schema）
- `aris_brain/psi_jspace_bridge/psi_bridge.py`（PSI cycle numpy 參考）
- `aris_brain/psi_jspace_bridge/README.md`（PSI 植入四級）
- `aris_brain/agi_kernel.py`（psilang_v2 / QuantumVM 介面 + PsiLang 語法）
- `aris_brain/psi_semiotics/psilang_hott.py`（PsiLang v3 HoTT 參考）
- `aris_brain/quantum_bridge.py`（QuantumPSI / QuantumMemory / PSI-N）
- `references/Harness-Consciousness-Engineering.md`（論文：模組清單 + 性能表）
