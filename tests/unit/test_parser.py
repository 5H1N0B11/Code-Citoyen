import pytest
import os
import json
from unittest.mock import patch, mock_open
from src.ingestion.vtt_parser import ingest_from_local_vtt

@pytest.fixture
def mock_vtt_content():
    return """WEBVTT

1
00:00:00.000 --> 00:00:03.000
Ceci est la première phrase.

2
00:00:03.500 --> 00:00:07.000
Deuxième phrase ici.

3
00:00:07.500 --> 00:00:10.000
Et enfin, la troisième phrase.
"""

@pytest.fixture(autouse=True)
def mock_nltk_resources():
    with patch("nltk.download") as mock_download:
        mock_download.return_value = True
        yield

@pytest.fixture(autouse=True)
def mock_nltk_sent_tokenize():
    # Patch sur la référence directe dans vtt_parser (pas sur nltk.tokenize)
    # Le mock ajoute le "." pour conserver le format de sortie attendu
    with patch(
        "src.ingestion.vtt_parser.sent_tokenize",
        side_effect=lambda text, language: [s.strip() + '.' for s in text.split(".") if s.strip()]
    ):
        yield


def test_ingest_from_local_vtt_success(mock_vtt_content):
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=mock_vtt_content)):
        entries = ingest_from_local_vtt("dummy.vtt")

        assert len(entries) == 3
        assert entries[0]['text'] == "Ceci est la première phrase."
        assert entries[0]['start'] == 0.0
        assert entries[1]['text'] == "Deuxième phrase ici."
        assert entries[1]['start'] == 3.5
        assert entries[2]['text'] == "Et enfin, la troisième phrase."
        assert entries[2]['start'] == 7.5
        assert all(entry.get('speaker') is None for entry in entries)


def test_ingest_from_local_vtt_empty_file():
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data="")):
        entries = ingest_from_local_vtt("empty.vtt")
        assert len(entries) == 0


def test_ingest_from_local_vtt_file_not_found():
    with patch("os.path.exists", return_value=False):
        entries = ingest_from_local_vtt("non_existent.vtt")
        assert len(entries) == 0


def test_ingest_from_local_vtt_with_speaker_tags():
    vtt_with_speaker = """WEBVTT

1
00:00:00.000 --> 00:00:04.000
<v Speaker 1>Bonjour à tous.

2
00:00:04.500 --> 00:00:08.000
<v Speaker 2>Bienvenue sur Code Citoyen.
"""
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=vtt_with_speaker)):
        entries = ingest_from_local_vtt("speaker.vtt")
        assert len(entries) == 2
        assert entries[0]['text'] == "Bonjour à tous."
        assert entries[0]['speaker'] == "Speaker 1"
        assert entries[1]['text'] == "Bienvenue sur Code Citoyen."
        assert entries[1]['speaker'] == "Speaker 2"


def test_ingest_from_local_vtt_complex_timestamps_and_breaks():
    """
    Teste un VTT avec des cues successifs — chaque cue devient une phrase distincte
    car le mock tokenize sur les '.' (une phrase par cue).
    """
    complex_vtt = """WEBVTT

1
00:00:00.000 --> 00:00:02.500
Première ligne.

2
00:00:02.501 --> 00:00:05.000
Suite de la phrase.

3
00:00:06.000 --> 00:00:08.000
Nouvelle phrase complète.
"""
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=complex_vtt)):
        entries = ingest_from_local_vtt("complex.vtt")
        assert len(entries) == 3
        assert entries[0]['text'] == "Première ligne."
        assert entries[0]['start'] == 0.0
        assert entries[1]['text'] == "Suite de la phrase."
        assert entries[1]['start'] == 2.501
        assert entries[2]['text'] == "Nouvelle phrase complète."
        assert entries[2]['start'] == 6.0
