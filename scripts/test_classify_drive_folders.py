#!/usr/bin/env python3
"""Offline tests for OIO Drive collection classification."""
import importlib.util, unittest
from pathlib import Path
SCRIPT=Path(__file__).with_name("classify_drive_folders.py")
SPEC=importlib.util.spec_from_file_location("classify_drive_folders",SCRIPT)
MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)

class ClassificationTests(unittest.TestCase):
    def test_folder_and_file_names_together_identify_series(self):
        files=[{"name":"S01E02.mkv","media_type":"video"}]
        category,group,reason=MODULE.classify_collection("Séries completas",files)
        self.assertEqual((category,group),("filmes_series","entertainment"))
    def test_cartoon_context_identifies_animation(self):
        files=[{"name":"episodio-01.mp4","media_type":"video"}]
        category,group,_=MODULE.classify_collection("Desenhos clássicos",files)
        self.assertEqual((category,group),("desenhos_animacoes","entertainment"))
    def test_music_audio_is_separated(self):
        files=[{"name":"faixa-01.mp3","media_type":"audio"}]
        category,group,_=MODULE.classify_collection("Discografia completa",files)
        self.assertEqual((category,group),("musicas","entertainment"))
    def test_unrelated_video_goes_to_misc_not_entertainment(self):
        files=[{"name":"TDA2003_Test.wmv","media_type":"video"}]
        category,group,_=MODULE.classify_collection("Pasta do Google Drive",files)
        self.assertEqual((category,group),("videos_diversos","misc"))
    def test_documents_are_not_media(self):
        self.assertEqual(MODULE.file_id_from_url("/file/d/ABC_123/view"),"ABC_123")
        self.assertNotIn(".pdf",MODULE.VIDEO)

if __name__=="__main__":unittest.main()
