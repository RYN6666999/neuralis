#!/usr/bin/env python3
"""Aris 演化閘門審查 CLI（list / show / approve / reject）。"""
import sys, os
sys.path.insert(0, os.path.expanduser("~/Developer/neuralis"))
from laap.evolve_gate import queue, show, approve, reject

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Aris 演化閘門審查")
    ap.add_argument("cmd", choices=["list", "show", "approve", "reject"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("reason", nargs="*", default=[])
    a = ap.parse_args()
    if a.cmd == "list":
        for t in queue():
            print(f"[{t['id']}] {t['status']} {t['iso']} {t['engine']}/{t['kind']}  note={t.get('note','')}")
            p = t.get("payload", {})
            print("   ", json_dumps(p)[:220])
    elif a.cmd == "show" and a.id:
        print(json_dumps(show(a.id)) if show(a.id) else f"票 {a.id} 不存在")
    elif a.cmd == "approve" and a.id:
        print("approved" if approve(a.id) else f"票 {a.id} 不存在")
    elif a.cmd == "reject" and a.id:
        print("rejected" if reject(a.id, " ".join(a.reason)) else f"票 {a.id} 不存在")

def json_dumps(o):
    import json
    return json.dumps(o, ensure_ascii=False)

if __name__ == "__main__":
    main()
