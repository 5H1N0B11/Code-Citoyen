import pytest
from src.utils import validate_text, AnalysisError, Config

def test_validate_text_valid_input():
    assert validate_text("Ceci est un texte valide.") is True

def test_validate_text_empty_input():
    with pytest.raises(AnalysisError, match="Le texte ne peut pas être vide."):
        validate_text("")

def test_validate_text_too_short_input():
    with pytest.raises(AnalysisError, match=f"Le texte est trop court, il doit contenir au moins {Config.MIN_CLAIM_LENGTH} caractères."):
        validate_text("court")

def test_validate_text_non_string_input():
    with pytest.raises(AnalysisError, match="Le texte doit être une chaîne de caractères."):
        validate_text(123)

def test_validate_text_dict_valid_text_key():
    assert validate_text({"text": "Ceci est un texte d'affirmation valide."}) is True

def test_validate_text_dict_valid_affirmation_key():
    assert validate_text({"affirmation": "Une autre affirmation valide ici."}) is True

def test_validate_text_dict_missing_keys():
    with pytest.raises(AnalysisError, match="Le texte ne peut pas être vide."):
        validate_text({"other_key": "some value"})

def test_validate_text_dict_empty_text_key():
    with pytest.raises(AnalysisError, match="Le texte ne peut pas être vide."):
        validate_text({"text": ""})

def test_validate_text_dict_none_text_key():
    with pytest.raises(AnalysisError, match="Le texte ne peut pas être vide."):
        validate_text({"text": None})

def test_validate_text_dict_too_short_text_key():
    with pytest.raises(AnalysisError, match=f"Le texte est trop court, il doit contenir au moins {Config.MIN_CLAIM_LENGTH} caractères."):
        validate_text({"text": "court"})

def test_validate_text_dict_non_string_text_key():
    with pytest.raises(AnalysisError, match="Le texte doit être une chaîne de caractères."):
        validate_text({"text": 123})

def test_validate_text_dict_non_string_affirmation_key():
    with pytest.raises(AnalysisError, match="Le texte doit être une chaîne de caractères."):
        validate_text({"affirmation": 123})

def test_validate_text_wrong_type_input():
    with pytest.raises(AnalysisError, match="Le texte doit être une chaîne de caractères ou un dictionnaire avec 'text'/'affirmation'."):
        validate_text([])

def test_validate_text_whitespace_only():
    with pytest.raises(AnalysisError, match="Le texte ne peut pas être vide."):
        validate_text("   \t\n  ")

def test_validate_text_dict_whitespace_only():
    with pytest.raises(AnalysisError, match="Le texte ne peut pas être vide."):
        validate_text({"text": "   \t\n  "})
