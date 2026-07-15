#!/usr/bin/env python3
"""Regression test for the multi-interval range fix in p3_tighten2.record_verdict.

Guards against the earlier 'keep-last' collapse, where a single OSV range whose
flat events list encodes two disjoint intervals (e.g. [1.0,1.2) and [2.0,2.5))
was reduced to only the last interval, wrongly EXCLUDING versions in the first.
Run: python3 results/major_revision/test_multiinterval.py  (exit 0 = pass)."""
import importlib.util, os
HERE=os.path.dirname(__file__)
spec=importlib.util.spec_from_file_location("p3t", os.path.join(HERE,"p3_tighten2.py"))
# import the module WITHOUT executing its __main__ CSV pass
import types, sys
src=open(os.path.join(HERE,"p3_tighten2.py")).read()
mod=types.ModuleType("p3t")
# strip the top-level driver (everything from the 'rows=' line onward)
head=src.split("\nrows=")[0]
exec(compile(head,"p3_tighten2.py","exec"), mod.__dict__)
rv=mod.record_verdict

def vuln_two_intervals():
    # one range, TWO intervals: [1.0,1.2) and [2.0,2.5)
    return {"affected":[{"package":{"ecosystem":"PyPI","name":"demo"},
        "ranges":[{"type":"ECOSYSTEM","events":[
            {"introduced":"1.0"},{"fixed":"1.2"},
            {"introduced":"2.0"},{"fixed":"2.5"}]}]}]}

v=vuln_two_intervals()
# Downstream coverage is decided by cw (well-formed IN-range hit): affected =
# cw or (cl and not ew). So the invariant we guard is cw for in-interval versions
# and not-cw for out-of-interval versions.
# version in FIRST interval must be covered (the keep-last bug returned cw=False here)
cw,ew,cl=rv("1.1", v, "demo");  assert cw, f"1.1 should be covered: {cw,ew,cl}"
# version in SECOND interval covered
cw,ew,cl=rv("2.3", v, "demo");  assert cw, f"2.3 should be covered: {cw,ew,cl}"
# version in the GAP [1.2,2.0): not covered by any interval
cw,ew,cl=rv("1.5", v, "demo");  assert not cw, f"1.5 should not be covered: {cw,ew,cl}"
# version above both intervals: not covered
cw,ew,cl=rv("3.0", v, "demo");  assert not cw, f"3.0 should not be covered: {cw,ew,cl}"
print("multi-interval regression: PASS (both intervals covered; gap + above not covered)")
