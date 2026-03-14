import pytest
import os
import json
from unittest.mock import patch, mock_open
from src.ingestion.vtt_parser import ingest_from_local_vtt
# Fixture pour simuler un contenu VTT minimal
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

# Mock de la fonction nltk.sent_tokenize pour éviter la dépendance au téléchargement
@pytest.fixture(autouse=True)
def mock_nltk_resources():
    # Mock nltk.download to prevent actual downloads during tests
    with patch("nltk.download") as mock_download:
        mock_download.return_value = True # Simulate successful download
        yield

@pytest.fixture(autouse=True)
def mock_nltk_sent_tokenize():
    with patch("nltk.tokenize.sent_tokenize", side_effect=lambda text, language: [s.strip() for s in text.split(".") if s.strip()]):
        yield

def test_ingest_from_local_vtt_success(mock_vtt_content):
    """
    Teste l'ingestion d'un fichier VTT local avec un contenu mocké.
    """
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=mock_vtt_content)) as mock_file:
        # On n'a pas besoin d'un vrai chemin, juste d'un nom pour mock_open
        entries = ingest_from_local_vtt("dummy.vtt")

        mock_file.assert_called_with("dummy.vtt", 'r', encoding='utf-8')

        assert len(entries) == 3
        assert entries[0]['text'] == "Ceci est la première phrase."
        assert entries[0]['start'] == 0.0
        assert entries[1]['text'] == "Deuxième phrase ici."
        assert entries[1]['start'] == 3.5
        assert entries[2]['text'] == "Et enfin, la troisième phrase."
        assert entries[2]['start'] == 7.5
        assert all('speaker' not in entry for entry in entries)

def test_ingest_from_local_vtt_empty_file():
    """
    Teste l'ingestion d'un fichier VTT vide.
    """
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data="")):
        entries = ingest_from_local_vtt("empty.vtt")
        assert len(entries) == 0

def test_ingest_from_local_vtt_file_not_found():
    """
    Teste le cas où le fichier VTT n'existe pas.
    """
    with patch("os.path.exists", return_value=False):
        entries = ingest_from_local_vtt("non_existent.vtt")
        assert len(entries) == 0

def test_ingest_from_local_vtt_with_speaker_tags():
    """
    Teste l'ingestion d'un fichier VTT avec des balises de locuteur.
    """
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
    Teste un VTT avec des timestamps complexes et des coupures.
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
        assert len(entries) == 2  # Deux phrases reconstituées
        assert entries[0]['text'] == "Première ligne. Suite de la phrase."
        assert entries[0]['start'] == 0.0
        assert entries[1]['text'] == "Nouvelle phrase complète."
        assert entries[1]['start'] == 6.0
