#!/usr/bin/env python3
"""Regression tests for V2 evidence, propagation, and version controls."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / name), *args, "--json"],
        check=False,
        capture_output=True,
        text=True,
    )


class EvidenceMatrixTests(unittest.TestCase):
    def write_matrix(self, path: Path, process: str) -> None:
        headers = [
            "sample_id",
            "sample_type",
            "composition_or_structure",
            "process",
            "mechanical_or_primary_performance",
            "microstructure_or_morphology",
            "dimension_or_residual_stress",
            "time_or_energy",
            "proof_purpose",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerow(
                {
                    "sample_id": "对比例1",
                    "sample_type": "对比例",
                    "composition_or_structure": "同实施例1",
                    "process": process,
                    "mechanical_or_primary_performance": "表3：数据",
                    "microstructure_or_morphology": "N/A：不用于组织对比",
                    "dimension_or_residual_stress": "表4：数据",
                    "time_or_energy": "缺失：P2待确认",
                    "proof_purpose": "验证创新特征A",
                }
            )

    def test_complete_matrix_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "matrix.csv"
            self.write_matrix(path, "同实施例1")
            result = run_script("audit_evidence_matrix.py", str(path))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_blank_comparator_process_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "matrix.csv"
            self.write_matrix(path, "")
            result = run_script("audit_evidence_matrix.py", str(path))
            self.assertEqual(result.returncode, 1)
            self.assertIn("INCOMPLETE_EVIDENCE_CELL", result.stdout)


class ParameterProvenanceTests(unittest.TestCase):
    def test_mosaic_range_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "parameters.csv"
            path.write_text(
                "claim_id,parameter,proposed_value,lower_source,upper_source,"
                "complete_combination_source,test_condition,mosaic_risk,status\n"
                "1,Mg,1.0-2.0,实施例1,实施例3,无完整组合,GB/T X,yes,confirmed\n",
                encoding="utf-8",
            )
            result = run_script("audit_parameter_provenance.py", str(path))
            self.assertEqual(result.returncode, 1)
            self.assertIn("MOSAIC_COMBINATION_RISK", result.stdout)

    def test_exact_value_with_complete_source_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "parameters.csv"
            path.write_text(
                "claim_id,parameter,proposed_value,lower_source,upper_source,"
                "complete_combination_source,test_condition,mosaic_risk,status\n"
                "2,Mg,1.5,实施例2,实施例2,实施例2完整配方,GB/T X,no,confirmed\n",
                encoding="utf-8",
            )
            result = run_script("audit_parameter_provenance.py", str(path))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class PropagationTests(unittest.TestCase):
    def test_stale_figure_text_export_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "正文.txt").write_text("新范围1.0-2.0；旧范围0.5-3.0", encoding="utf-8")
            manifest = {
                "files": ["正文.txt"],
                "forbidden_terms": ["旧范围0.5-3.0"],
                "required_terms": ["新范围1.0-2.0"],
            }
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            result = run_script("audit_revision_propagation.py", str(path))
            self.assertEqual(result.returncode, 1)
            self.assertIn("STALE_TERM", result.stdout)


class VersionBundleTests(unittest.TestCase):
    def test_valid_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            formal = root / "申请文件V2.txt"
            formal.write_text("正式文本", encoding="utf-8")
            digest = hashlib.sha256(formal.read_bytes()).hexdigest()
            manifest = {
                "version": "V2",
                "status": "formal-source",
                "files": [
                    {"role": "formal-source", "path": formal.name, "sha256": digest}
                ],
            }
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            result = run_script("audit_version_bundle.py", str(path))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unconfirmed_compiled_data_cannot_be_submission_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            formal = root / "申请文件V2.txt"
            formal.write_text("正式文本", encoding="utf-8")
            digest = hashlib.sha256(formal.read_bytes()).hexdigest()
            manifest = {
                "version": "V2",
                "status": "submission-ready",
                "contains_compiled_data": True,
                "files": [
                    {"role": "formal-source", "path": formal.name, "sha256": digest}
                ],
            }
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            result = run_script("audit_version_bundle.py", str(path))
            self.assertEqual(result.returncode, 1)
            self.assertIn("COMPILED_DATA_NOT_CONFIRMED", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
