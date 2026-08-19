#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aris-gate.py — 人肉閘門儀表板（地圖 vs 疆域一覽）

用途：把「地圖≠疆域」的檢查成本降到『掃一眼紅綠』。
Ryan = 人類裁判（最後那顆原子），只看顏色就下閘。

對帳標準（可證偽）：
  綠 ✓  = 地圖說 & 疆域實測一致
  紅 ✗  = 不一致（地圖騙人 or 疆域被改）→ 擋下
  灰 ?  = 還沒實測（誠實標未驗證，禁冒充）

每一格都附「怎麼知道的」（來源檔:行），查無來源標 UNSOURCED。
本版 v1：territory 為人工實測填表（08-14）；之後可加自動量測餵這張表。
"""
import html, json, pathlib, datetime

OUT = "/Users/ryan/aris-gate.html"

# 每列：{consumer, map_says, territory, verdict, evidence}
# territory = 機器實測（before/after mtime 量測, 2026-08-14 20:5x）
ROWS = [
    dict(
        consumer="startup.py 開機 backend",
        map_says="RustPsiBackend (startup.py:50, env=rust)",
        territory="RustPsiBackend → read rust-latest.json",
        verdict="ok",
        evidence="laap/startup.py:55；aris-truth check_effective_backend（這條是 startup 自己，範圍內對）",
    ),
    dict(
        consumer="/v1/cognitive_state (Hermes 注入)",
        map_says="aris-truth 報 effective=rust",
        territory="psi_jspace_bridge → psi_state.json（NEEDS 回傳全 0.50）",
        verdict="bad",
        evidence="機器實測:POST 後 psi_state.json mtime+581ms、needs=0.50（≠rust 的 0.87/0.94）；laap_brain_api.py:324→_get_psi_adapter→psi_hermes_adapter",
    ),
    dict(
        consumer="/v1/chat/completions (對話)",
        map_says="(無明確宣稱 / 跟 effective=rust 打架)",
        territory="aris_cognitive_bridge → cognitive_bridge.json",
        verdict="bad",
        evidence="機器實測:POST 後 cognitive_bridge.json mtime+27.3s、input_queue/latest/quantum/telemetry 動、psi_state 未動；laap_brain_api.py process_with_laap",
    ),
    dict(
        consumer="quantum_output writer",
        map_says="latest.json 優先，無則 rust",
        territory="對話時 latest.json + quantum_output.json 皆被寫/讀",
        verdict="warn",
        evidence="機器實測:chat 後兩檔 mtime 都動；laap/quantum_output.py:80 `_read(LATEST) or _read(RUST)`",
    ),
    dict(
        consumer="aris-autoupdate",
        map_says="直讀 rust-latest.json",
        territory="腳本內 hardcode rust-latest.json",
        verdict="ok",
        evidence="scripts/aris-autoupdate.sh:20,65",
    ),
]

now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
VN = {"ok":"✓ 綠", "bad":"✗ 紅", "warn":"⚠ 黃", "bad_unknown":"✗ 紅(未定)"}
COLOR = {"ok":"#1a7f37","bad":"#d1242f","warn":"#b08800","bad_unknown":"#d1242f"}
BG    = {"ok":"#e6f4ea","bad":"#fde8e8","warn":"#fdf6e3","bad_unknown":"#fde8e8"}

summary_good = sum(1 for r in ROWS if r["verdict"]=="ok")
summary_bad  = sum(1 for r in ROWS if r["verdict"] in ("bad","bad_unknown"))
summary_warn = sum(1 for r in ROWS if r["verdict"]=="warn")

rows_html=[]
for r in ROWS:
    v=r["verdict"]
    rows_html.append(f"""
<tr>
  <td style="padding:10px 12px;border:1px solid #ddd;font-weight:600">{html.escape(r['consumer'])}</td>
  <td style="padding:10px 12px;border:1px solid #ddd;font-family:monospace;font-size:12px">{html.escape(r['map_says'])}</td>
  <td style="padding:10px 12px;border:1px solid #ddd;font-family:monospace;font-size:12px">{html.escape(r['territory'])}</td>
  <td style="padding:10px 12px;border:1px solid #ddd;text-align:center;background:{BG[v]};color:{COLOR[v]};font-weight:800;font-size:18px">{VN[v]}</td>
  <td style="padding:8px 10px;border:1px solid #ddd;font-size:11px;color:#555">{html.escape(r['evidence'])}</td>
</tr>""")

page=f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>Aris 人肉閘門 — 地圖 vs 疆域</title></head>
<body style="font-family:-apple-system,'PingFang TC',sans-serif;margin:24px;background:#fafafa">
<h1 style="margin:0 0 4px">Aris 接線閘門 · 地圖 vs 疆域</h1>
<div style="color:#888;margin-bottom:12px">執行人類裁判：Ryan　|　產出時間：{now}　|　判準：綠=對帳過、紅=地圖≠疆域、黃=警訊、灰=未實測</div>
<div style="font-size:20px;margin-bottom:16px">
  總覽：
  <span style="background:{BG['ok']};color:{COLOR['ok']};padding:4px 10px;border-radius:6px;font-weight:800">{summary_good} 綠</span>
  <span style="background:{BG['bad']};color:{COLOR['bad']};padding:4px 10px;border-radius:6px;font-weight:800">{summary_bad} 紅</span>
  <span style="background:{BG['warn']};color:{COLOR['warn']};padding:4px 10px;border-radius:6px;font-weight:800">{summary_warn} 黃</span>
</div>
<table style="border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.08)">
<thead><tr style="background:#eee">
<th style="padding:10px 12px;border:1px solid #ddd;text-align:left">端點 / 消費者</th>
<th style="padding:10px 12px;border:1px solid #ddd;text-align:left">地圖說（宣稱）</th>
<th style="padding:10px 12px;border:1px solid #ddd;text-align:left">疆域實測（實際）</th>
<th style="padding:10px 12px;border:1px solid #ddd">對帳</th>
<th style="padding:10px 12px;border:1px solid #ddd;text-align:left">證據（來源:行）</th>
</tr></thead>
<tbody>{''.join(rows_html)}</tbody></table>
<p style="color:#999;font-size:11px;margin-top:10px">輸出：{OUT}　·　v1 人工實測填表；可延伸自動量測（lsof/mtime before-after）餵此表，讓疆域自證。</p>
</body></html>"""

pathlib.Path(OUT).write_text(page, encoding="utf-8")
print("written", OUT, len(page), "bytes")
