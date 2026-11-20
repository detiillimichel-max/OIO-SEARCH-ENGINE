#!/usr/bin/env python3
"""Offline regression tests for the public Drive HTML parser."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("classify_drive_folders.py")
SPEC = importlib.util.spec_from_file_location("classify_drive_folders", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ListingParserTests(unittest.TestCase):
    def test_nested_div_does_not_close_parent_entry_early(self):
        html = """
        <div class="flip-entry" data-id="FILE123" title="Video.mp4">
          <div class="inner"><span>Video.mp4</span></div>
          <div><a href="/file/d/FILE123/view">Video.mp4</a></div>
        </div>
        """
        files = MODULE.extract_files(html)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["id"], "FILE123")
        self.assertEqual(files[0]["category"], "videos")

    def test_standard_drive_file_link_is_extracted(self):
        html = '<a href="https://drive.google.com/file/d/ABC_123/view">Aula.mp3</a>'
        files = MODULE.extract_files(html)
        self.assertEqual(files[0]["id"], "ABC_123")
        self.assertEqual(files[0]["category"], "musicas")

    def test_document_is_recognized_but_not_as_media(self):
        self.assertEqual(MODULE.classify_name("catalogo.pdf"), "documentos_outros")
        self.assertEqual(MODULE.classify_name("filme.mkv"), "videos")


if __name__ == "__main__":
    unittest.main()
