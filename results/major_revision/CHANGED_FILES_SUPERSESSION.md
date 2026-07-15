# Superseded intermediate file

`residual_12_audit.csv` in this directory is a **pre-correction** intermediate: it was the
row-level audit of the original 12 silent-PASS P3 cases and carries annotations such as
"remains valid pre-PR P3". Those annotations are **superseded** by the final
`changed_rows_final.csv`, in which all ten of those P3 rows are verdict `FP_temporal`
(false positives whose only covering advisory postdates the PR). The corrected silent-PASS
set is 7 = 2 boundary P2 + 5 recovered false negatives (see `CORRECTION_NOTICE.md`).

Authoritative source for every corrected label: **`changed_rows_final.csv`**. The
`residual_12_audit.csv` file is retained only for provenance of the audit that first
surfaced the systematic defect; do not read its annotations as final labels.
