#!/usr/bin/env python3
"""Self-tests for the patent review conversion and format-audit tools."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import docx_to_md


SCRIPT_DIR = Path(__file__).resolve().parent
AUDIT_SCRIPT = SCRIPT_DIR / "audit_patent_format.py"
CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
DOCUMENT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
  <w:body>
    <w:p><w:r><w:t>普通正文</w:t></w:r></w:p>
    <w:sdt><w:sdtContent>
      <w:p><w:r><w:t>内容控件中的关键技术特征</w:t></w:r></w:p>
    </w:sdtContent></w:sdt>
    <w:p><w:r><w:t>公式：</w:t></w:r>
      <m:oMath><m:r><m:t>E=mc²</m:t></m:r></m:oMath>
    </w:p>
    <w:p><w:ins><w:r><w:t>保留的插入内容</w:t></w:r></w:ins>
      <w:del><w:r><w:delText>排除的删除内容</w:delText></w:r></w:del>
      <w:moveFrom><w:r><w:t>移动前内容</w:t></w:r></w:moveFrom>
      <w:moveTo><w:r><w:t>移动后内容</w:t></w:r></w:moveTo>
    </w:p>
    <w:sectPr/>
  </w:body>
</w:document>
"""
FOOTNOTES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:footnote w:id="1"><w:p><w:r><w:t>脚注技术条件</w:t></w:r></w:p></w:footnote>
</w:footnotes>
"""
VALID_PATENT = """# 说明书

## 技术领域
测试技术。

## 背景技术
现有技术。

## 发明内容
测试方案。

## 具体实施方式
测试实施方式。

# 权利要求书

1. 一种测试装置，其特征在于，包括处理器。

2. 根据权利要求1所述的测试装置，其特征在于，还包括传感器。

# 说明书摘要
测试摘要。
"""
INVALID_PATENT = VALID_PATENT.replace(
    "2. 根据权利要求1", "3. 根据权利要求4"
)


def make_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("word/document.xml", DOCUMENT_XML)
        archive.writestr("word/footnotes.xml", FOOTNOTES_XML)
        archive.writestr("word/media/image1.png", b"test")


class DocxConversionTests(unittest.TestCase):
    def test_extracts_content_controls_math_notes_and_visible_revisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.docx"
            make_docx(source)
            result = docx_to_md.convert(source, revision_mode="accepted")
            self.assertIn("内容控件中的关键技术特征", result.markdown)
            self.assertIn("E=mc²", result.markdown)
            self.assertIn("脚注技术条件", result.markdown)
            self.assertIn("保留的插入内容", result.markdown)
            self.assertIn("移动后内容", result.markdown)
            self.assertNotIn("排除的删除内容", result.markdown)
            self.assertNotIn("移动前内容", result.markdown)
            self.assertTrue(any("公式" in warning for warning in result.warnings))
            self.assertTrue(any("媒体" in warning for warning in result.warnings))
            self.assertTrue(any("修订" in warning for warning in result.warnings))

            original = docx_to_md.convert(source, revision_mode="original")
            self.assertIn("排除的删除内容", original.markdown)
            self.assertIn("移动前内容", original.markdown)
            self.assertNotIn("保留的插入内容", original.markdown)
            self.assertNotIn("移动后内容", original.markdown)

    def test_requires_explicit_revision_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.docx"
            make_docx(source)
            with self.assertRaisesRegex(ValueError, "revision-mode"):
                docx_to_md.convert(source)

    def test_refuses_to_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "existing.md"
            destination.write_text("original", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                docx_to_md.write_markdown(destination, "replacement")
            self.assertEqual(destination.read_text(encoding="utf-8"), "original")
            docx_to_md.write_markdown(destination, "replacement", force=True)
            self.assertEqual(destination.read_text(encoding="utf-8"), "replacement")

    def test_default_output_uses_separate_temp_directory(self) -> None:
        source = Path("/example/formal.docx")
        destination = docx_to_md.default_destination(source)
        self.assertEqual(destination.name, "formal.md")
        self.assertNotEqual(destination.parent, source.parent)


class FormatAuditTests(unittest.TestCase):
    def run_audit(self, text: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "申请文件.md"
            source.write_text(text, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(AUDIT_SCRIPT), str(source), "--json"],
                check=False,
                capture_output=True,
                text=True,
            )

    def test_valid_application_passes(self) -> None:
        result = self.run_audit(VALID_PATENT)
        self.assertEqual(result.returncode, 0)
        self.assertIn('"errors": 0', result.stdout)

    def test_invalid_claim_number_and_reference_fail(self) -> None:
        result = self.run_audit(INVALID_PATENT)
        self.assertEqual(result.returncode, 1)
        self.assertIn("CLAIM_NUMBERING", result.stdout)
        self.assertIn("MISSING_CLAIM_REFERENCE", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
