from backend.app.ingest.search_text import expand_identifiers, split_identifier


def test_pascal_case():
    assert split_identifier("SignatureExpired") == ["signature", "expired"]


def test_snake_case():
    assert split_identifier("get_signature") == ["get", "signature"]


def test_acronym_followed_by_word():
    assert split_identifier("HTTPServer") == ["http", "server"]


def test_digits_are_separate():
    assert split_identifier("base64") == ["base", "64"]


def test_expand_keeps_whole_name_and_parts():
    assert expand_identifiers("raise SignatureExpired(") == "raise signatureexpired signature expired"


def test_single_word_is_not_duplicated():
    assert expand_identifiers("return value") == "return value"