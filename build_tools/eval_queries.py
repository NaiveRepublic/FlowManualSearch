"""Quick quality check: does the expected section appear in the top 3?"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from search_engine import ManualIndex

CASES = [
    ("How do I connect Flow to the device?", "8.2"),
    ("switch to dark mode", "1.7"),
    ("make a copy of a filter", ["4.4", "5.4", "13.5"]),
    ("flip the polarity of a channel", "5.3.7"),
    ("stop the signal from getting too loud", ["14", "14.1", "11.5", "16.1"]),
    ("automatic volume levelling", ["16", "16.1"]),
    ("where can I see the log", "8.5"),
    ("what windows version do I need", "1.2"),
    ("switch quickly between two setups", "11.8"),
    ("repeat part of a song", "11.9.3"),
    ("install a newer version of Flow", "1.8"),
    ("add room echo", ["15", "15.1", "15.2"]),
    ("prevent a filter from being changed", ["4.3.4", "5.3.10", "13.4.6"]),
    ("set the Q factor", "2.2.4"),
    ("biquad gain range", ["2.2.3"]),
    ("import filters from FilterLab", ["6.2", "6.2.3", "6.2.4", "6.1"]),
    ("diff two workspaces", ["12.2", "12.3", "12.1"]),
    ("export files for the DSP", ["9.2", "9.3", "9.1"]),
    ("who can use the software, licensing", "1.3"),
    ("mute an output channel", ["5.3.2", "13.4.1"]),
    ("CPU load measurement", "8.4"),
    ("pink noise test signal", "10.2.3"),
    ("bypass a processor", "1.6.5"),
    ("map input channels to outputs", ["11.4", "10.2.4", "5.1"]),
    ("how fast does an interface parameter change, ramp", ["7.4.2", "11.2"]),
]
idx = ManualIndex(Path(__file__).resolve().parents[1] / "app" / "data")
hits1 = hits3 = 0
t = time.time()
for q, exp in CASES:
    exp = [exp] if isinstance(exp, str) else exp
    r = idx.search(q)["results"]
    got = [x["section"] for x in r]
    h1 = got[:1] and got[0] in exp
    h3 = any(g in exp for g in got[:3])
    hits1 += bool(h1); hits3 += bool(h3)
    print(("OK " if h3 else "XX ") + f"{q!r:55} -> {got[:3]}  want {exp}")
print(f"\ntop-1 {hits1}/{len(CASES)}   top-3 {hits3}/{len(CASES)}   avg {1000*(time.time()-t)/len(CASES):.1f} ms/query")
