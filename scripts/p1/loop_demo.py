import random
random.seed(7)
MEMS=["a","b","c","d"]
MEM_FEAT={"a":{"a1","a2","客戶"},"b":{"b1","b2","客戶"},"c":{"c1","c2","約"},"d":{"d1","d2","約"}}
def gen_query(m):
    pool=list(MEM_FEAT[m]); n=random.choice([1,2]); return " ".join(random.sample(pool,n)), m
def trial(feat_gran, epochs=15, per=300, LR=0.1, LD=0.06, WR=0.015, WD=0.015):
    W={(m,f):1.0 for m in MEMS for f in MEM_FEAT[m]}
    errs=[]
    for _ in range(epochs):
        c=0
        for _ in range(per):
            q,true=gen_query(random.choice(MEMS)); toks=q.split()
            def score(m): return sum(W[(m,f)] for f in toks if f in MEM_FEAT[m])
            top=max(MEMS,key=score); ok=(top==true)
            if ok: c+=1
            for f in toks:
                if feat_gran:
                    if f in MEM_FEAT[true]: W[(true,f)]+=LR
                    if f in MEM_FEAT[top] and not ok: W[(top,f)]-=LD
                else:
                    if ok: 
                        for ff in MEM_FEAT[true]: W[(true,ff)]+=WR
                    else:
                        for ff in MEM_FEAT[top]: W[(top,ff)]-=WD
        errs.append(1-c/per)
    return errs
ew=trial(False); eg=trial(True)
print("winner-only (v1：0.44岬急):", " ".join(f"{e:.3f}" for e in ew))
print("feat-granular (新):      ", " ".join(f"{e:.3f}" for e in eg))