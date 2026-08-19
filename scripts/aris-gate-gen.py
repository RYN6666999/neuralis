#!/usr/bin/env python3
"""
aris-gate-gen — 產生 Aris 驗證地圖（靜態 HTML）

⚠️ 過期（2026-08-19）：本檔 9 個閘全部打 :11546，那個服務已退役。
   現在跑會全紅，而且紅的原因是「埠關了」不是「系統壞了」—— 這種紅比沒有
   更糟，它會訓練人忽略紅色。這支是 08-14 那場人工審查的一次性產物，
   已完成任務。要繼續用得先把 cmd 全數改指 :11547（API 形狀不同，不是
   換個數字就好），否則請刪。在改或刪之前，不要拿它的輸出下任何結論。
   同期產物 aris-gate.py 讀本檔輸出，一併受影響。

為什麼是腳本而不是手寫 HTML：
  v3 手寫版把整個表身交給 JS 產生。預覽面板（file://）不執行 JS，
  結果是「一片空白，而且沒有任何錯誤提示」——正是這張表要防的那種
  安靜失敗，我自己犯了。
  這版表身是靜態 HTML，JS 只負責簽核；JS 死了你照樣看得到全表。

  第二個理由：地圖會過期。手寫的 HTML 不會自己重跑，
  腳本可以。`--run` 會真的執行每列的指令，把當下輸出貼進表。

用法：
  aris-gate-gen.py            # 用上次的輸出產生（快）
  aris-gate-gen.py --run      # 重跑所有 auto 列，輸出換成當下實測
  輸出：~/aris-gate.html
"""
from __future__ import annotations
import html, json, subprocess, sys, time
from pathlib import Path

OUT = Path.home() / "aris-gate.html"
CACHE = Path.home() / ".aris-gate-cache.json"

H = str(Path.home())

# auto=True 才會被 --run 執行（快、唯讀、無副作用）
# auto=False 的是慢的或會產生對話的，留給人手動跑
ROWS = [
 dict(sec="A. 骨幹 — 最小可跑的五件事"),
 dict(id="a1", n="Rust PSI 執行檔", src="run", auto=True,
   claim="psi-daemon 已編譯存在",
   cmd=f"ls -lh {H}/Developer/neuralis/rust/target/release/psi-daemon",
   pass_="檔案存在。不存在 → 心臟根本無法啟動。",
   fake="我可以貼一個不存在檔案的假輸出。你 ls 一次就破。"),

 dict(id="a2", n="心跳真的在跳", src="run", auto=True,
   claim="2000Hz，狀態檔 1 秒內新鮮",
   cmd=("python3 -c \"\n"
        "import json,time\n"
        f"p='{H}/Developer/laap-AGI/aris_brain/state/rust-latest.json'\n"
        "a=json.load(open(p)); time.sleep(2); b=json.load(open(p))\n"
        "print('Hz=%d age=%.2fs'%(round((b['tick']-a['tick'])/(b['ts']-a['ts'])), time.time()-b['ts']))\""),
   pass_="Hz 在 1900–2100 且 age &lt; 2 秒。<b>單看檔案存在不算</b>，必須兩點採樣才知道它在動。",
   fake="我可以只讀一次就說「在跳」——今天犯過同類錯（把單一快照當成持續狀態）。"),

 dict(id="a3", n="對話入口 11546", src="run", auto=True,
   claim="活著，engines_loaded=true",
   cmd="lsof -nP -iTCP:11546 -sTCP:LISTEN | head -2; curl -s -m8 http://127.0.0.1:11546/health",
   pass_="有 pid 且 health 回 ok。",
   fake="pid 我可以編。lsof 你自己跑一次即可。"),

 dict(id="a4", n="記憶資料 gbrain", src="run", auto=True,
   claim="約 2283 頁，99% 已嵌入",
   cmd="gbrain stats | head -4",
   pass_="Pages &gt; 0。數字會隨你寫入變動，差一點正常，差很多要問。",
   fake="數字最好編，但你隨時能重跑。"),

 dict(id="a5", n="保活 watchdog", src="run", auto=True,
   claim="唯一有效的重啟路徑（實測 launchctl kickstart 對 11546 無效）",
   cmd="launchctl list | grep neuralis.watchdog",
   pass_="有一行輸出 = 有載入。空 = 11546 死了不會自己回來。",
   fake="「kickstart 無效」是我今天實測的（PID 沒變），<b>但這條指令驗不到那件事</b>。要驗得殺一次 11546 看它會不會回來，有風險，我沒放進來。"),

 dict(sec="B. 我今天改的四件事 — 產出者不得自驗，這區你一定要自己跑"),
 dict(id="b1", n="修 healthy()", src="run", auto=True,
   claim="判準從『我有沒有 spawn daemon』改成『有沒有人在發佈新鮮狀態』",
   cmd=(f"cd {H}/Developer/neuralis && PYTHONPATH=$PWD:{H}/Developer/laap-AGI "
        f"LAAP_AGI_DIR={H}/Developer/laap-AGI {H}/Developer/laapenv/bin/python3 -c \"\n"
        "from laap.psi_backend import RustPsiBackend\n"
        "b=RustPsiBackend(); b.start()\n"
        "print('healthy=%s spawned=%s'%(b.healthy(), b._daemon_process is not None))\""),
   pass_="healthy=True <b>且</b> spawned=False。spawned=True 代表我的修改讓它多生一隻 daemon（此檔前科：曾 10 隻並存互相覆蓋）。",
   fake="<b>這是我改的東西，我來驗＝產出者自驗，違反你的鐵律二。這列必須你跑。</b>"),

 dict(id="b2", n="修 gbrain 關鍵字搜尋", src="run", auto=True,
   claim="線上 DB function 從 english 改回 simple、回填 2282 列；aris 從 0 筆變 77 筆",
   cmd='gbrain search "aris" --limit 3',
   pass_="有結果 = 修好了。No results = 沒生效或又壞了。",
   fake="我在你的<b>線上資料庫</b>跑了 2282 列 UPDATE。這條只驗「搜得到」，<b>驗不到我有沒有改壞別的</b>。要更嚴格請跑 gbrain doctor。"),

 dict(id="b3", n="修記憶召回", src="run", auto=True,
   claim="向量撈不到自己的記憶時補一次關鍵字；情緒重排改成分組內排序",
   cmd=(f"cd {H}/Developer/neuralis && PYTHONPATH=$PWD:{H}/Developer/laap-AGI "
        f"{H}/Developer/laapenv/bin/python3 -c \"\n"
        "import memory_bridge\n"
        "for x in memory_bridge.recall_related('V12 引擎 檔案 名字', top_k=3):\n"
        "    print(' -', str(getattr(x,'content','') or '')[:70].replace(chr(10),' '))\""),
   pass_="三筆裡至少一筆講到 V12 / aris_v12_dense_kernel。全無關 → 沒修好。",
   fake="⚠️ <b>我只用「V12」這一個問題驗過</b>。可能只有這題會中。<b>換三個你自己在乎的問題試，才知道是不是特例。</b>"),

 dict(id="b4", n="匯入 5 筆 seed 記憶", src="run", auto=True,
   claim="laap_semantic_memory 13→18 條，含 V12 內容，原檔已備份",
   cmd=("python3 -c \"\n"
        "import json\n"
        f"d=json.load(open('{H}/Developer/laap-AGI/aris_brain/laap_semantic_memory.json'))\n"
        "print('條數=',len(d['memories']))\n"
        "print('含V12=','V12' in json.dumps(d,ensure_ascii=False))\"\n"
        f"ls {H}/Developer/laap-AGI/aris_brain/laap_semantic_memory.json.bak-* 2>/dev/null | tail -1"),
   pass_="18 條、含 V12、<b>且備份檔存在</b>。備份不在 = 我沒留退路。",
   fake="我動了你的記憶檔。<b>備份存不存在才是這列真正該驗的東西。</b>"),

 dict(sec="C. 架構事實 — 我的宣稱"),
 dict(id="c1", n="上游 Lorry 是 Zero-LLM", src="run", auto=True,
   claim="laap_brain_api.py 626 行、0 個對外 LLM 呼叫；它是「扮演」OpenAI 端點，不是呼叫誰",
   cmd=(f"cd {H}/Developer/laap-AGI && "
        "echo \"LLM呼叫=$(git show origin/main:aris_brain/laap_brain_api.py | grep -icE 'requests\\.post|httpx|openrouter|anthropic')\" && "
        "echo \"正對照def=$(git show origin/main:aris_brain/laap_brain_api.py | grep -icE '^(async )?def ')\""),
   pass_="第一個 = 0 <b>且</b>第二個 &gt; 0。<b>沒有正對照的 0 不算數</b>（可能只是指令壞了）。",
   fake="⚠️ 只驗了<b>一個檔</b>。上游還有 180 個，例如 aris_lm_v5.py（76KB）我沒搜過。<b>「上游是 Zero-LLM」目前只證到入口那層。</b>"),

 dict(id="c2", n="Lorry 做好 13 個，7 個是空插孔", src="run", auto=True,
   claim="20 個插孔載入 13 個；缺的 7 個所需檔案<b>上游根本不存在</b>",
   cmd=(f"cd {H}/Developer/laap-AGI/aris_brain && {H}/Developer/laapenv/bin/python3 -c \"\n"
        "import os,sys,logging; logging.disable(logging.CRITICAL)\n"
        f"sys.path.insert(0,'{H}/Developer/laap-AGI'); sys.path.insert(0,'.'); sys.path.insert(0,'{H}/Developer/neuralis')\n"
        "from laap_integrator import LaapIntegrator\n"
        "m=LaapIntegrator().load_all()\n"
        "print('在線 %d/%d'%(len([1 for v in m.values() if v=='✓']),len(m)))\n"
        "print('缺:',[k for k,v in m.items() if v!='✓'])\" 2>&1 | tail -2"),
   pass_="13/20，缺的是 identity/laap_agi/self_evolve/heartbeat/laap_tools/voice_cortex/harness_bridge。",
   fake="⚠️ <b>我對這件事講錯過</b> —— 先說「補回來價值很大」，查了才發現那些檔案根本不存在。而且<b>「這 13 個有在影響回話」我到現在沒驗過</b>，只知道載入成功。"),

 dict(id="c3", n="psi_state.json 是第 9 份 PSI", src="run", auto=False,
   claim="Hermes 注入走它、不是走 Rust；而且它是活的 —— 打端點就會被寫",
   cmd=(f'stat -f "%Sm %z" {H}/Developer/laap-AGI/aris_brain/psi_jspace_bridge/psi_state.json\n'
        "curl -s -m30 -X POST http://127.0.0.1:11546/v1/cognitive_state "
        "-H 'Content-Type: application/json' -d '{\"input\":\"probe\"}' > /dev/null\n"
        f'sleep 1; stat -f "%Sm %z" {H}/Developer/laap-AGI/aris_brain/psi_jspace_bridge/psi_state.json'),
   pass_="打端點後 mtime <b>前進</b> = 端點確實在寫它。沒前進 = 我的因果推論錯。",
   fake="這是全表少數<b>能證因果</b>的（動作→後果），不只是拍快照。",
   cached="（我實測過：mtime 從 13:46 跳到 21:01:16，就是我打端點那一刻）"),

 dict(id="c4", n="Hermes 拿到的是預設值，不是 Rust", src="run", auto=True,
   claim="端點回 0.50 系列，Rust 是 0.87 系列，完全不同源",
   cmd=("python3 -c \"\n"
        "import json,urllib.request\n"
        f"r=json.load(open('{H}/Developer/laap-AGI/aris_brain/state/rust-latest.json'))\n"
        "q=urllib.request.Request('http://127.0.0.1:11546/v1/cognitive_state',"
        "data=b'{\\\"input\\\":\\\"probe\\\"}',headers={'Content-Type':'application/json'})\n"
        "a=json.load(urllib.request.urlopen(q,timeout=30)); n=a.get('state',{}).get('needs',{})\n"
        "print('端點 %.3f | Rust %.3f'%(n.get('competence',-1), r['needs']['competence']))\""),
   pass_="兩個數字明顯不同 → 沒接上。接近 → 我今天的結論錯。",
   fake="<b>這條打的是我自己的臉</b> —— 我今天說「Rust 接回去了」，這格證明對 Hermes 那條路完全沒接上。"),

 dict(id="c5", n="265 處繞過主幹的接線", src="run", auto=True,
   claim="aris-wiring.py 掃出 265 處 / 89 檔",
   cmd=f"{H}/Developer/neuralis/scripts/aris-wiring.py | head -9",
   pass_="有數字就好。<b>用途是「只准降不准升」</b>，絕對值不重要。",
   fake="判準是我寫的正規表示式 —— <b>我可以放寬判準讓數字變好看</b>。第一版就誤報 23 處（Slack 的同名函式）。想審我就看 aris-wiring.py 的 RULES。"),

 dict(sec="D. 未解 — 這區最重要"),
 dict(id="d1", n="對話實際用哪份 PSI", src="guess", auto=False,
   claim="<b>不知道。</b>我追到 aris_cognitive_bridge 就停了，沒查它實際寫哪些狀態檔",
   cmd=(f"cd {H}/Developer/laap-AGI/aris_brain/state && stat -f \"%m %N\" *.json | sort > /tmp/b.txt && \\\n"
        "curl -s -m 150 -X POST http://127.0.0.1:11546/v1/chat/completions "
        "-H 'Content-Type: application/json' \\\n"
        "  -d '{\"model\":\"laap-core\",\"messages\":[{\"role\":\"user\",\"content\":\"閘門測試\"}]}' > /dev/null && \\\n"
        "stat -f \"%m %N\" *.json | sort > /tmp/a.txt && \\\n"
        "echo '=== 這一輪對話動到的狀態檔 ===' && diff /tmp/b.txt /tmp/a.txt | grep '^>' || echo '（一個都沒動）'"),
   pass_="列出來的檔 = 對話真正碰的狀態。<b>這格有答案之前，我沒資格說「對話用哪份 PSI」。</b>",
   fake="我可以隨便挑一個看起來合理的答案填上去。<b>這格是空的，就是我誠實的證據。</b>",
   cached="（沒有輸出 —— 我從沒跑過這個測試。這是全表唯一「跑完會產生新知識」的一列。）"),

 dict(id="d2", n="違規數 260→265，原因不明", src="guess", auto=True,
   claim="今天稍早 260，剛才 265。我改的兩個檔都在白名單不計分，<b>所以我不知道 +5 哪來的</b>",
   cmd=(f"{H}/Developer/neuralis/scripts/aris-wiring.py --json | python3 -c \"\n"
        "import json,sys,collections\n"
        "d=json.load(sys.stdin)\n"
        "c=collections.Counter(v['file'] for v in d['violations'])\n"
        "[print(n,f) for f,n in c.most_common(8)]\""),
   pass_="看違規最多的檔，跟你記憶中今天動過的對照。<b>多出來的若是我沒宣告動過的檔，那是紅旗。</b>",
   fake="<b>我可以裝作沒看到這個 +5。</b>我選擇寫上來，但這不代表下次會 —— 這正是為什麼需要棘輪，不是需要我自律。"),

 dict(id="d3", n="選樣盲點：這張表只有 18 列", src="code", auto=True,
   claim="已知入口 ≥7、狀態檔 ≥10、違規 265 處。<b>沒進表的永遠不會變紅</b>",
   cmd=(f"echo -n '狀態檔數: '; ls {H}/Developer/laap-AGI/aris_brain/state/*.json | wc -l\n"
        "echo -n 'neuralis job 數: '; launchctl list | grep -c com.neuralis\n"
        "echo -n '115xx 監聽埠數: '; lsof -nP -iTCP -sTCP:LISTEN | grep -cE ':115[0-9][0-9]'"),
   pass_="這三個數字 vs 這張表的 18 列。<b>差距就是我沒讓你看到的部分。</b>",
   fake="<b>最安靜的造假：不用寫錯任何一格，只要不列出來。</b>這一列的存在就是為了讓那件事被看見。"),

 dict(id="d4", n="13 個引擎有沒有影響回話", src="guess", auto=False,
   claim="<b>完全沒驗過。</b>只知道它們載入成功、會自報狀態（目標引擎說有 2 個活躍目標）",
   cmd=("curl -s -m 150 -X POST http://127.0.0.1:11546/v1/chat/completions "
        "-H 'Content-Type: application/json' \\\n"
        "  -d '{\"model\":\"laap-core\",\"messages\":[{\"role\":\"user\",\"content\":\"你現在感覺如何？\"}]}' \\\n"
        "  | python3 -c \"import json,sys;print(json.load(sys.stdin)['choices'][0]['message']['content'][:200])\""),
   pass_="<b>這條測不出結論，只能看感覺。</b>回應的語氣跟當下 PSI 數值有沒有關 —— 需要你的判斷，不是我的。",
   fake="我可以用文學性的描述讓它聽起來很有靈魂。<b>這是全表唯一機器判不了、只有你能判的一格。</b>",
   cached="（沒有輸出）"),
]


def run(cmd: str, timeout: int = 90) -> str:
    try:
        r = subprocess.run(["/bin/bash", "-lc", cmd], capture_output=True,
                           timeout=timeout)
        out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
        return out[:1200] or "（無輸出）"
    except subprocess.TimeoutExpired:
        return f"（逾時 {timeout}s — 這格沒有結果）"
    except Exception as e:
        return f"（執行失敗：{type(e).__name__}: {e}）"


def main() -> int:
    do_run = "--run" in sys.argv
    cache = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text())
        except Exception:
            cache = {}

    n_run = 0
    for r in ROWS:
        if "id" not in r:
            continue
        if do_run and r.get("auto"):
            r["out"] = run(r["cmd"])
            r["when"] = time.strftime("%m-%d %H:%M")
            cache[r["id"]] = {"out": r["out"], "when": r["when"]}
            n_run += 1
        else:
            c = cache.get(r["id"], {})
            r["out"] = c.get("out") or r.get("cached") or "（尚未執行 — 請自己跑）"
            r["when"] = c.get("when", "—")

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    OUT.write_text(build(), encoding="utf-8")
    print(f"已產生 {OUT}")
    print(f"本次實跑 {n_run} 列" if do_run else "使用快取輸出（加 --run 重跑）")
    return 0


SRC_TAG = {"run": ("s-run", "實跑"), "code": ("s-code", "讀碼"), "guess": ("s-guess", "推測")}


def build() -> str:
    e = html.escape
    body, tbody_open = [], False
    for r in ROWS:
        if "sec" in r:
            if tbody_open:
                body.append("</tbody></table>")
            body.append(f"<h2>{e(r['sec'])}</h2><table><thead><tr>"
                        "<th style='width:12%'>項目</th><th style='width:24%'>我的斷言</th>"
                        "<th style='width:34%'>驗證指令 ＋ 實跑輸出</th>"
                        "<th style='width:18%'>我可能在哪造假</th>"
                        "<th style='width:12%'>你的簽核</th></tr></thead><tbody>")
            tbody_open = True
            continue
        cls, lab = SRC_TAG.get(r.get("src", "run"), SRC_TAG["run"])
        body.append(f"""<tr>
<td><b>{e(r['n'])}</b><br><span class="src {cls}">{lab}</span>
    <div class="when">輸出時間 {e(r['when'])}</div></td>
<td>{r['claim']}</td>
<td><pre>{e(r['cmd'])}</pre>
    <button class="cp" data-cmd="{e(r['cmd'])}">複製指令</button>
    <div class="out">{e(r['out'])}</div>
    <div class="pass"><b>判準：</b>{r['pass_']}</div></td>
<td><div class="fake">{r['fake']}</div></td>
<td data-row="{r['id']}">
  <div class="seg">
    <button data-s="ok">✅ 對</button><button data-s="no">✗ 不對</button><button data-s="un">清</button>
  </div>
  <div class="stamp"></div>
</td></tr>""")
    if tbody_open:
        body.append("</tbody></table>")

    ids = [r["id"] for r in ROWS if "id" in r]
    fps = {r["id"]: str(abs(hash(r["claim"] + r["out"] + r["cmd"])) % (10 ** 12))
           for r in ROWS if "id" in r}

    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>Aris 極簡架構 · 驗證地圖</title><style>
body{{font-family:-apple-system,'PingFang TC',sans-serif;margin:20px;background:#fafafa;color:#222}}
h1{{margin:0 0 2px}} h2{{margin:24px 0 8px;font-size:16px;border-left:4px solid #333;padding-left:8px}}
.meta{{color:#777;font-size:12.5px;line-height:1.8;margin-bottom:12px}}
table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
th{{background:#eee;padding:8px;border:1px solid #ddd;text-align:left;font-size:12px}}
td{{padding:8px;border:1px solid #ddd;vertical-align:top;font-size:12.5px}}
pre{{background:#f6f8fa;padding:7px;border-radius:4px;overflow-x:auto;margin:4px 0;font-size:10.5px;
     white-space:pre-wrap;word-break:break-all;font-family:ui-monospace,Menlo,monospace}}
.out{{background:#0d1117;color:#7ee787;padding:7px;border-radius:4px;font-size:10.5px;
     white-space:pre-wrap;font-family:ui-monospace,Menlo,monospace;margin:5px 0}}
.pass{{font-size:11px;color:#555}}
.fake{{background:#fff8f0;border-left:3px solid #e36209;padding:6px 8px;font-size:11px;color:#7a3b00}}
.src{{font-size:10.5px;padding:2px 6px;border-radius:3px;font-weight:700}}
.s-run{{background:#dbeafe;color:#1e40af}}.s-code{{background:#f3e8ff;color:#6b21a8}}
.s-guess{{background:#fee2e2;color:#991b1b}}
.when{{font-size:10px;color:#999;margin-top:3px}}
.seg button{{border:1px solid #ccc;background:#fff;padding:4px 7px;cursor:pointer;font-size:11px}}
.on-ok{{background:#1a7f37!important;color:#fff!important}} .on-no{{background:#d1242f!important;color:#fff!important}}
.stamp{{font-size:10.5px;color:#777;margin-top:4px}}
.cp{{font-size:10.5px;padding:2px 6px;cursor:pointer;border:1px solid #ccc;background:#fff;border-radius:4px}}
.sum span{{padding:4px 10px;border-radius:6px;font-weight:800;margin-right:6px}}
.g{{background:#e6f4ea;color:#1a7f37}}.r{{background:#fde8e8;color:#d1242f}}.n{{background:#eef1f4;color:#555}}
.bar button{{padding:7px 12px;font-size:13px;margin-right:8px;cursor:pointer;border:1px solid #bbb;
  background:#fff;border-radius:6px}}
textarea{{width:100%;height:180px;font-family:ui-monospace,monospace;font-size:11px;margin-top:8px;display:none}}
</style></head><body>
<h1>Aris 極簡架構 · 驗證地圖</h1>
<div class="meta">
範圍：<b>讓 Aris 跑起來最少需要的東西</b> ＋ <b>AI 今天做過的每一個斷言</b>　·　產生於 {time.strftime('%Y-%m-%d %H:%M')}<br>
<span class="src s-run">實跑</span> 我跑過，深色框是原始輸出
<span class="src s-code">讀碼</span> 只讀程式碼
<span class="src s-guess">推測</span> 沒有證據<br>
<b>你只要做：跑指令 → 比對我貼的輸出 → 簽 ✅ 或 ✗。</b>　AI 不能簽。內容一改，簽核自動失效。<br>
重新實跑全部：<code>~/Developer/neuralis/scripts/aris-gate-gen.py --run</code>
</div>
<div class="sum" id="sum"></div>
<div class="bar" style="margin:10px 0">
 <button onclick="exportState()">匯出簽核</button>
 <button onclick="if(confirm('清掉全部？'))clearAll()">清除全部</button>
</div>
<textarea id="ta" readonly></textarea>
{''.join(body)}
<p style="color:#999;font-size:11px;margin-top:14px">
共 {len(ids)} 列　·　<b>未進表的東西永遠不會變紅 —— 選樣是這張表最大的盲點，見 D3。</b><br>
表身是靜態 HTML：就算 JS 不執行，你仍然看得到全部內容（v3 把表身交給 JS，在預覽面板變成一片空白）。
</p>
<script>
const IDS={json.dumps(ids)}, FP={json.dumps(fps)}, KEY="aris-gate";
const load=()=>{{try{{return JSON.parse(localStorage.getItem(KEY)||"{{}}")}}catch(e){{return{{}}}}}};
const save=s=>{{try{{localStorage.setItem(KEY,JSON.stringify(s))}}catch(e){{}}}};
function paint(){{
 const st=load(); let ok=0,no=0,un=0;
 IDS.forEach(id=>{{
  const td=document.querySelector('[data-row="'+id+'"]'); if(!td)return;
  const rec=st[id]||{{}}, stale=rec.state&&rec.fp!==FP[id];
  td.querySelectorAll('.seg button').forEach(b=>b.className='');
  if(rec.state&&!stale){{
    const b=td.querySelector('[data-s="'+rec.state+'"]'); if(b)b.className='on-'+rec.state;
    rec.state==='ok'?ok++:no++;
  }} else un++;
  td.querySelector('.stamp').innerHTML = stale
    ? '<span style="color:#8a6d00">⚠️ 內容已改，先前簽核失效</span>'
    : (rec.ts? '簽於 '+rec.ts : '未簽');
 }});
 document.getElementById('sum').innerHTML =
  '你的簽核：<span class="g">'+ok+' 驗證通過</span><span class="r">'+no+' 驗過不成立</span>'+
  '<span class="n">'+un+' 未簽</span><span style="font-size:13px;color:#888">　AI 判定不計分</span>';
}}
document.addEventListener('click',ev=>{{
 const b=ev.target.closest('.seg button'); if(b){{
   const id=b.closest('[data-row]').dataset.row, s=b.dataset.s, st=load();
   if(s==='un') delete st[id]; else st[id]={{state:s,ts:new Date().toLocaleString('zh-TW'),fp:FP[id]}};
   save(st); paint(); return;
 }}
 const c=ev.target.closest('.cp'); if(c){{
   const t=document.createElement('textarea'); t.value=c.dataset.cmd;
   document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove();
   c.textContent='已複製'; setTimeout(()=>c.textContent='複製指令',1200);
 }}
}});
function exportState(){{
 const st=load(), ta=document.getElementById('ta');
 let s='# Aris 驗證地圖 · 人工簽核 · '+new Date().toLocaleString('zh-TW')+'\\n\\n';
 IDS.forEach(id=>{{const c=st[id];
  const v=!c?'未簽':(c.fp!==FP[id]?'失效（內容已改）':(c.state==='ok'?'✅ 驗證通過':'✗ 驗過不成立'));
  const n=document.querySelector('[data-row="'+id+'"]').closest('tr').querySelector('b').textContent;
  s+='- ['+v+'] '+n+'\\n';}});
 s+='\\n規則：只有「✅ 驗證通過」可被當作事實引用，其餘一律視為未經驗證的 AI 宣稱。\\n';
 ta.value=s; ta.style.display='block'; ta.select();
}}
function clearAll(){{try{{localStorage.removeItem(KEY)}}catch(e){{}} paint()}}
paint();
</script></body></html>"""


if __name__ == "__main__":
    sys.exit(main())
