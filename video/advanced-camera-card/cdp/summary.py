import json,sys
d=json.load(open(sys.argv[1]))
print("build rnd | hidden on enter ms | 1st fs frame h/vh @t | full at | leave events | leave: hidden? | 1st frame after leave (top,h) | heights after")
for v,runs in d.items():
    for i,r in enumerate(runs):
        en=r["enter"]; le=r["leave"]
        ev=en["events"]; h=[e[0] for e in ev if e[1]=="visibilitychange" and e[2]=="hidden"]; vv=[e[0] for e in ev if e[1]=="visibilitychange" and e[2]=="visible"]
        hid=f"{vv[0]-h[0]}" if h and vv else "-"
        fs=[f for f in en["frames"] if f[2]==1]
        first=fs[0] if fs else None; full=next((f[0] for f in fs if f[4]>=f[5]-1),None)
        lev=[(e[0],e[1]) for e in le["events"] if e[1] in("fullscreenchange","visibilitychange","resize")]
        lh=any(e[1]=="visibilitychange" and e[2]=="hidden" for e in le["events"])
        nf=[f for f in le["frames"] if f[2]==0]
        fst=f"{first[4]}/{first[5]} @{first[0]}" if first else "none"
        print(f"{v:4} {i+1} | {hid:>4} | {fst} | {full} | {lev} | {lh} | {(nf[0][3],nf[0][4]) if nf else None} | {sorted(set(f[4] for f in nf))}")
