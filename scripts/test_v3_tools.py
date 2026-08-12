#!/usr/bin/env python3
"""Regression tests for V3 claim, method, and semantic-delta controls."""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_script(name: str, path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / name), str(path), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


class ClaimAntecedentTests(unittest.TestCase):
    headers = [
        "claim_id",
        "depends_on",
        "element",
        "element_role",
        "antecedent_claim",
        "wording",
        "relation_change",
        "notes",
    ]

    def test_valid_inherited_element_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "claims.csv"
            write_csv(
                path,
                self.headers,
                [
                    {
                        "claim_id": "1",
                        "depends_on": "",
                        "element": "试件",
                        "element_role": "new",
                        "antecedent_claim": "",
                        "wording": "试件",
                        "relation_change": "none",
                        "notes": "",
                    },
                    {
                        "claim_id": "2",
                        "depends_on": "1",
                        "element": "试件",
                        "element_role": "inherited",
                        "antecedent_claim": "1",
                        "wording": "所述试件",
                        "relation_change": "none",
                        "notes": "",
                    },
                ],
            )
            result = run_script("audit_claim_antecedent_basis.py", path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('"errors": 0', result.stdout)

    def test_sibling_branch_cannot_supply_antecedent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "claims.csv"
            write_csv(
                path,
                self.headers,
                [
                    {
                        "claim_id": "2",
                        "depends_on": "1",
                        "element": "底板",
                        "element_role": "new",
                        "antecedent_claim": "",
                        "wording": "微动底板",
                        "relation_change": "none",
                        "notes": "",
                    },
                    {
                        "claim_id": "5",
                        "depends_on": "1",
                        "element": "底板",
                        "element_role": "inherited",
                        "antecedent_claim": "2",
                        "wording": "所述微动底板",
                        "relation_change": "none",
                        "notes": "",
                    },
                ],
            )
            result = run_script("audit_claim_antecedent_basis.py", path)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ANTECEDENT_OUTSIDE_DEPENDENCY_PATH", result.stdout)

    def test_reintroduced_element_is_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "claims.csv"
            write_csv(
                path,
                self.headers,
                [
                    {
                        "claim_id": "1",
                        "depends_on": "",
                        "element": "滑台",
                        "element_role": "new",
                        "antecedent_claim": "",
                        "wording": "微动滑台",
                        "relation_change": "none",
                        "notes": "",
                    },
                    {
                        "claim_id": "5",
                        "depends_on": "1",
                        "element": "滑台",
                        "element_role": "reintroduced",
                        "antecedent_claim": "1",
                        "wording": "微动滑台",
                        "relation_change": "none",
                        "notes": "",
                    },
                ],
            )
            result = run_script("audit_claim_antecedent_basis.py", path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REINTRODUCED_ELEMENT", result.stdout)


class MethodAlignmentTests(unittest.TestCase):
    headers = [
        "step_id",
        "claim_text",
        "spec_text",
        "figure_text",
        "pre_state",
        "post_state",
        "prerequisites",
        "status",
        "notes",
    ]

    @staticmethod
    def row(step_id: str, status: str = "aligned") -> dict[str, str]:
        return {
            "step_id": step_id,
            "claim_text": "执行步骤",
            "spec_text": "执行步骤",
            "figure_text": "执行步骤",
            "pre_state": "准备状态",
            "post_state": "完成状态",
            "prerequisites": "N/A：首步骤或前一步已完成",
            "status": status,
            "notes": "",
        }

    def test_aligned_sequential_steps_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "steps.csv"
            write_csv(path, self.headers, [self.row("S1"), self.row("S2")])
            result = run_script("audit_method_step_alignment.py", path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nonsequential_steps_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "steps.csv"
            write_csv(path, self.headers, [self.row("S1"), self.row("S3")])
            result = run_script("audit_method_step_alignment.py", path)
            self.assertEqual(result.returncode, 1)
            self.assertIn("NON_SEQUENTIAL_STEPS", result.stdout)

    def test_declared_conflict_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "steps.csv"
            write_csv(path, self.headers, [self.row("S1", "order-conflict")])
            result = run_script("audit_method_step_alignment.py", path)
            self.assertEqual(result.returncode, 1)
            self.assertIn("UNRESOLVED_STEP_CONFLICT", result.stdout)


class SemanticDeltaTests(unittest.TestCase):
    headers = [
        "change_id",
        "location",
        "before",
        "after",
        "change_level",
        "added_relations",
        "removed_relations",
        "scope_effect",
        "authorization",
        "source_basis",
        "status",
    ]

    @staticmethod
    def row(**overrides: str) -> dict[str, str]:
        row = {
            "change_id": "C001",
            "location": "权利要求1",
            "before": "包括滑台",
            "after": "包括所述滑台",
            "change_level": "B",
            "added_relations": "N/A：仅修复指代",
            "removed_relations": "N/A：无",
            "scope_effect": "none",
            "authorization": "N/A：B级同步修复",
            "source_basis": "权利要求1",
            "status": "confirmed",
        }
        row.update(overrides)
        return row

    def test_b_level_relation_change_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "delta.csv"
            write_csv(
                path,
                self.headers,
                [
                    self.row(
                        after="滑台设置在底板上",
                        added_relations="设置在",
                        scope_effect="narrowed",
                    )
                ],
            )
            result = run_script("audit_revision_semantic_delta.py", path)
            self.assertEqual(result.returncode, 1)
            self.assertIn("RELATION_CHANGE_REQUIRES_C", result.stdout)

    def test_confirmed_c_level_change_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "delta.csv"
            write_csv(
                path,
                self.headers,
                [
                    self.row(
                        after="滑台设置在底板上",
                        change_level="C",
                        added_relations="设置在",
                        scope_effect="narrowed",
                        authorization="confirmed",
                    )
                ],
            )
            result = run_script("audit_revision_semantic_delta.py", path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_undeclared_relation_term_warns(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "delta.csv"
            write_csv(
                path,
                self.headers,
                [
                    self.row(
                        after="包括滑台，滑台设置在底板上",
                        change_level="C",
                        scope_effect="uncertain",
                        authorization="confirmed",
                    )
                ],
            )
            result = run_script("audit_revision_semantic_delta.py", path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("UNDECLARED_RELATION_TERM", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
