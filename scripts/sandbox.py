#!/usr/bin/env python3
"""sandbox.py — Phase 1-3 合併。子命令：analyze | plan | sandbox | ccp
Ponytail: 只要 JSON，不要 YAML。砍 docstring 到一行。"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CASES = REPO / "docs/specs/aris-sandbox-learning/cases"
SB_ROOT = Path("/tmp/aris-sandboxes")
SB_INDEX = SB_ROOT / ".index.json"
SB_MAX = 3
# 沙箱憑證隔離白名單
_SAFE = frozenset({"PATH","HOME","USER","SHELL","TERM","LANG","LC_ALL","TMPDIR",
  "NEURALIS_AGENCY_INTERVAL","NEURALIS_AGENCY_MAX_PER_HOUR","NEURALIS_AGENCY_DELEGATE",
  "NEURALIS_CONSTITUTION","NEURALIS_CONSOLIDATION","NEURALIS_AGENCY_HOURLY_TOKEN_BUDGET",
  "NEURALIS_LLM_MODEL","NEURALIS_TOOL_MODEL","NEURALIS_CHAT_TOOLS","AGENTOS_EXECUTOR_REGISTRY"})


def _git(args, cwd=None):
    return subprocess.run(["git"]+args, cwd=str(cwd or REPO), capture_output=True, text=True, check=True).stdout.strip()
def _gq(args, cwd=None):
    return subprocess.run(["git"]+args, cwd=str(cwd or REPO), capture_output=True, text=True).returncode == 0
def _head():
    return _git(["rev-parse","--short","HEAD"])
def _load():
    return json.loads(SB_INDEX.read_text()) if SB_INDEX.exists() else {"sb":[],"nid":1}
def _save(d):
    SB_ROOT.mkdir(parents=True, exist_ok=True); SB_INDEX.write_text(json.dumps(d,indent=2))
def _find(sid):
    for s in _load()["sb"]:
        if s["id"]==sid: return s
    return None
def _clean_env():
    return {k:v for k,v in os.environ.items() if k in _SAFE}


# ── analyze ──
def cmd_analyze(rng="HEAD~5..HEAD"):
    """萃取 commit 資訊，產出 CCP 雛形。"""
    hashes = [l.split()[0] for l in _git(["log","--oneline","--no-decorate",rng]).strip().splitlines() if l.strip()]
    out = []
    for h in hashes:
        raw = _git(["log","-1","--format=%H%n%an%n%ae%n%ai%n%s%n%b",h]).split("\n",5)
        dif = _git(["diff","--stat",f"{h}~1..{h}"])
        files = [{"s":l[0],"p":l[1]} for l in (l.split("\t",1) for l in _git(["diff","--name-status",f"{h}~1..{h}"]).strip().split("\n")) if len(l)==2]
        dom = set()
        kw = {"safety-gate":["safety_gate"],"agency":["agency.py"],"psi-core":["psi_core"],"s-span":["s_span"],"scream-channel":["scream-"],"tests":["tests/"],"docs":["docs/"]}
        for f in files:
            for d,k in kw.items():
                if any(kk in f["p"] for kk in k): dom.add(d)
        out.append({"hash":h,"author":raw[1],"date":raw[3],"subject":raw[4],"body":raw[5][:200] if len(raw)>5 else "","domains":sorted(dom) if dom else ["other"],"files":files})
    return out


# ── plan ──
def cmd_plan(problem, target, approach=None, effort="medium"):
    """產出結構化實作計畫（diff 為空）。"""
    pid = f"PLAN-{max([int(p.stem.split('-')[1]) for p in CASES.glob('plan-*.json')]+[0])+1:03d}"
    files = [f.strip() for f in target.split(",")]
    return {"plan_id":pid,"generated_at":datetime.now(timezone.utc).isoformat(),"phase":"2-suggestion",
      "problem":problem,"target":files,"approach":approach or f"修改 {', '.join(files)}",
      "effort":effort,"base_commit":_head(),"diff":None}


# ── sandbox ──
def cmd_sandbox_create(reason, plan=None):
    idx = _load()
    if len([s for s in idx["sb"] if s["status"]=="active"]) >= SB_MAX:
        print("沙箱上限",file=sys.stderr); sys.exit(1)
    sid = f"{idx['nid']:03d}"; idx["nid"]+=1
    slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason.lower())[:30]
    d = SB_ROOT / f"sb-{sid}-{slug}"
    d.mkdir(parents=True,exist_ok=True)
    _git(["worktree","add","--detach",str(d),"HEAD"])
    d.joinpath(".sb-start").write_text(str(time.time()))
    info = {"id":sid,"status":"active","ts":datetime.now(timezone.utc).isoformat(),"reason":reason,
      "plan":plan,"base":_head(),"path":str(d),"commits":[],"test":{}}
    idx["sb"].append(info); _save(idx)
    print(json.dumps(info,indent=2)); return info

def cmd_sandbox_destroy(sid):
    info = _find(sid)
    if not info: print(f"無沙箱 {sid}",file=sys.stderr); sys.exit(1)
    d = Path(info["path"])
    if d.exists():
        subprocess.run(["git","worktree","remove","--force",str(d)],cwd=str(REPO),capture_output=True)
        if d.exists(): shutil.rmtree(d,ignore_errors=True)
    idx = _load()
    for s in idx["sb"]:
        if s["id"]==sid: s["status"]="dead"; s["dead_at"]=datetime.now(timezone.utc).isoformat()
    _save(idx)

def cmd_sandbox_list(fmt="json"):
    sb = _load()["sb"]
    if fmt=="json": print(json.dumps(sb,indent=2)); return
    for s in sb:
        ex = "✅" if Path(s.get("path","")).exists() else "❌"
        print(f"{s['id']:6} {s['status']:10} {s.get('reason','')[:40]:40} {ex}")

def cmd_sandbox_test(sid, passed, failed):
    info = _find(sid)
    if not info: print(f"無沙箱 {sid}",file=sys.stderr); sys.exit(1)
    idx = _load()
    for s in idx["sb"]:
        if s["id"]==sid: s["test"]={"passed":passed,"failed":failed}
    _save(idx)

def cmd_ccp(sid):
    info = _find(sid)
    if not info: print(f"無沙箱 {sid}",file=sys.stderr); sys.exit(1)
    d = Path(info["path"])
    if not d.exists(): print(f"目錄不存: {d}",file=sys.stderr); sys.exit(1)
    try: log = _git(["log","--oneline",f"{info['base']}..HEAD"],cwd=d)
    except: log = ""
    commits = [{"h":l.split()[0],"m":" ".join(l.split()[1:])} for l in log.strip().split("\n") if l.strip()]
    try: stat = _git(["diff","--stat",f"{info['base']}..HEAD"],cwd=d)
    except: stat = ""
    try: diff = _git(["diff",f"{info['base']}..HEAD"],cwd=d)
    except: diff = ""
    try: files = [{"s":l[0],"p":l[2]} for l in (l.split("\t",1) for l in _git(["diff","--name-status",f"{info['base']}..HEAD"],cwd=d).strip().split("\n")) if len(l)==2]
    except: files = []
    return {"ccp_id":f"CCP-{sid}","sandbox_id":sid,"base":info["base"],"commits":commits,
      "files":files,"diff":diff,"diff_lines":len(diff.split("\n")),"test":info.get("test",{})}


# ── main ──
def main():
    p = argparse.ArgumentParser(description="sandbox.py — Phase 1-3 工具鏈")
    p.add_argument("--format",choices=["json","text"],default="json")
    sub = p.add_subparsers(dest="cmd",required=True)

    a = sub.add_parser("analyze"); a.add_argument("--range",default="HEAD~5..HEAD")
    a.add_argument("--output","-o")

    pl = sub.add_parser("plan"); pl.add_argument("--problem",required=True)
    pl.add_argument("--target",required=True); pl.add_argument("--approach")
    pl.add_argument("--effort",choices=["small","medium","large"],default="medium")
    pl.add_argument("--output","-o")

    sc = sub.add_parser("sandbox"); sc.add_argument("action",choices=["create","destroy","list","test"])
    sc.add_argument("--reason","-r"); sc.add_argument("--plan","-p")
    sc.add_argument("--id"); sc.add_argument("--passed",type=int,default=0)
    sc.add_argument("--failed",type=int,default=0)

    cc = sub.add_parser("ccp"); cc.add_argument("--id",required=True); cc.add_argument("--output","-o")

    args = p.parse_args()

    if args.cmd == "analyze":
        out = cmd_analyze(args.range)
        if args.output: Path(args.output).write_text(json.dumps(out,indent=2,ensure_ascii=False))
        else: print(json.dumps(out,indent=2,ensure_ascii=False))

    elif args.cmd == "plan":
        out = cmd_plan(args.problem,args.target,args.approach,args.effort)
        if args.output: Path(args.output).write_text(json.dumps(out,indent=2,ensure_ascii=False))
        else: print(json.dumps(out,indent=2,ensure_ascii=False))

    elif args.cmd == "sandbox":
        if args.action=="create": cmd_sandbox_create(args.reason,args.plan)
        elif args.action=="destroy": cmd_sandbox_destroy(args.id)
        elif args.action=="list": cmd_sandbox_list(args.format)
        elif args.action=="test": cmd_sandbox_test(args.id,args.passed,args.failed)

    elif args.cmd == "ccp":
        out = cmd_ccp(args.id)
        if args.output: Path(args.output).write_text(json.dumps(out,indent=2,ensure_ascii=False))
        else: print(json.dumps(out,indent=2,ensure_ascii=False))

if __name__ == "__main__":
    main()