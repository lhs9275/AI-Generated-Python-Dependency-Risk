"""Regression checks for the strict-offline RQ3 source of truth."""
import csv
import unittest
from pathlib import Path

from pipeline.analysis import compute_hybrid_study_tables as hybrid
from pipeline.analysis import export_manuscript_tables as exporter


ROOT = Path(__file__).resolve().parents[1]
RQ3_CSV = ROOT / "results" / "tables" / "table_rq3_gate_effect.csv"
TABLE_IV_CSV = ROOT / "results" / "metrics_v2" / "table5_baseline_ladder_v2.csv"
TSE_STATS = ROOT / "results" / "tse_stats.json"


class Rq3StrictSourceTest(unittest.TestCase):
    def test_qwen_b3_afsp_is_strict_offline(self):
        rows = {row["model"]: row for row in hybrid.build_rq3()}
        afsp = float(rows["Qwen-7B"]["AFSP"])
        self.assertAlmostEqual(afsp, 0.5208, delta=1e-3)
        self.assertNotAlmostEqual(afsp, 0.5333, delta=1e-3)

    def test_exported_afsp_matches_fresh_strict_regeneration(self):
        fresh = {row["model"]: row for row in hybrid.build_rq3()}
        with RQ3_CSV.open(newline="", encoding="utf-8") as f:
            exported = {row["model"]: row for row in csv.DictReader(f)}
        self.assertEqual(set(exported), set(fresh))
        for model, row in fresh.items():
            self.assertAlmostEqual(
                float(exported[model]["AFSP"]), float(row["AFSP"]), delta=1e-9
            )

    def test_rq3_and_table_iv_share_published_strict_b3_afsp(self):
        expected = {
            "Qwen-7B": ("Qwen2.5-Coder-7B-Instruct", 0.5208),
            "Qwen-14B": ("Qwen2.5-Coder-14B-Instruct-AWQ", 0.5417),
            "Qwen-32B": ("Qwen2.5-Coder-32B-Instruct-AWQ", 0.6083),
            "DeepSeek-6.7B": ("deepseek-coder-6.7b-instruct", 0.5375),
            "CodeLlama-7B": ("CodeLlama-7b-Instruct-hf", 0.3667),
        }
        rq3 = {row["model"]: row for row in hybrid.build_rq3()}
        with TABLE_IV_CSV.open(newline="", encoding="utf-8") as f:
            table_iv = {
                row["model"]: row
                for row in csv.DictReader(f)
                if row["mode"] == "B3"
            }

        for rq3_model, (table_iv_model, value) in expected.items():
            self.assertAlmostEqual(float(rq3[rq3_model]["AFSP"]), value, delta=1e-3)
            self.assertAlmostEqual(
                float(table_iv[table_iv_model]["afsp_all"]), value, delta=1e-3
            )

    def test_rq3_pipeline_does_not_read_proxy_csv(self):
        for module in (hybrid, exporter):
            source = Path(module.__file__).read_text(encoding="utf-8")
            self.assertNotIn("additional_baselines.csv", source)
            self.assertNotIn("_load_additional_baselines", source)

    def test_manuscript_tables_and_tse_stats_exclude_old_afsp_values(self):
        paths = list((ROOT / "results" / "tables").rglob("*")) + [TSE_STATS]
        for path in paths:
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("0.5333", text, path)
                self.assertNotIn("0.4042", text, path)


if __name__ == "__main__":
    unittest.main()
