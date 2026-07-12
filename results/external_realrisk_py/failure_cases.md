# Failure cases — risky records not blocked by B3

Reported honestly; any miss is a finding, not hidden. A WARN means the risk WAS detected but fell below the blocking-severity policy threshold (surfaced to the developer, not gated); a PASS means undetected.


## Detected-but-warned (sub-threshold severity)

- [S3] `flask==3.1.0` (direct_cve, GHSA-4grg-w6v8-c28g) fired=['S3', 'S3']

## Undetected (B3 PASS) — true misses

- **None — B3 detected every risky record in this corpus.**

## Risky caught by B3 but missed by S1+S2+S3 (full-guard added value)

- None: S1+S2+S3 core already catches everything B3 catches here.
