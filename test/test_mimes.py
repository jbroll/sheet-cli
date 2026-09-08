"""Tests for drive_cli.mimes — extension and export mimeType tables (offline)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from drive_cli import mimes

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class TestSourceMime:
    def test_known_extension(self):
        assert mimes.source_mime("flyer.docx") == DOCX
        assert mimes.source_mime("data.csv") == "text/csv"
        assert mimes.source_mime("deck.pptx") == PPTX

    def test_extension_is_case_insensitive(self):
        assert mimes.source_mime("FLYER.DOCX") == DOCX

    def test_full_path_uses_only_the_extension(self):
        assert mimes.source_mime("/a/b/c/notes.txt") == "text/plain"

    def test_unknown_extension_is_none(self):
        assert mimes.source_mime("archive.wat") is None

    def test_extensionless_path_is_none(self):
        assert mimes.source_mime("data") is None


class TestNativeTarget:
    def test_word_processing_converts_to_doc(self):
        assert mimes.native_target(DOCX) == mimes.DOC_MIME
        assert mimes.native_target("text/plain") == mimes.DOC_MIME
        assert mimes.native_target("text/markdown") == mimes.DOC_MIME

    def test_spreadsheet_converts_to_sheet(self):
        assert mimes.native_target(XLSX) == mimes.SHEET_MIME
        assert mimes.native_target("text/csv") == mimes.SHEET_MIME

    def test_presentation_converts_to_slides(self):
        assert mimes.native_target(PPTX) == mimes.SLIDES_MIME

    def test_no_equivalent_is_none(self):
        assert mimes.native_target("application/pdf") is None
        assert mimes.native_target("image/png") is None


class TestExportMime:
    def test_doc_to_pdf(self):
        assert mimes.export_mime(mimes.DOC_MIME, "out.pdf") == "application/pdf"

    def test_doc_to_docx(self):
        assert mimes.export_mime(mimes.DOC_MIME, "out.docx") == DOCX

    def test_sheet_to_csv(self):
        assert mimes.export_mime(mimes.SHEET_MIME, "out.csv") == "text/csv"

    def test_slides_to_pptx(self):
        assert mimes.export_mime(mimes.SLIDES_MIME, "out.pptx") == PPTX

    def test_extension_is_case_insensitive(self):
        assert mimes.export_mime(mimes.DOC_MIME, "OUT.PDF") == "application/pdf"

    def test_extension_invalid_for_the_type_lists_the_valid_ones(self):
        with pytest.raises(ValueError, match="epub"):
            mimes.export_mime(mimes.DOC_MIME, "out.xlsx")

    def test_extensionless_output_raises(self):
        with pytest.raises(ValueError):
            mimes.export_mime(mimes.DOC_MIME, "out")

    def test_non_native_type_raises(self):
        with pytest.raises(ValueError, match="cannot export"):
            mimes.export_mime("application/pdf", "out.pdf")

    def test_native_type_with_no_exports_raises(self):
        with pytest.raises(ValueError, match="cannot export"):
            mimes.export_mime("application/vnd.google-apps.folder", "out.pdf")


class TestAliases:
    def test_three_aliases(self):
        assert mimes.NATIVE_BY_ALIAS == {
            "doc": mimes.DOC_MIME,
            "sheet": mimes.SHEET_MIME,
            "slides": mimes.SLIDES_MIME,
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
