import pytest

from backend.app.answer.judge import parse_verdict


def test_valid_verdict():
    assert parse_verdict('{"covered": [true, false, true]}', 3) == [True, False, True]


def test_wrong_number_of_verdicts_is_an_error():
    with pytest.raises(ValueError):
        parse_verdict('{"covered": [true]}', 3)


def test_malformed_json_is_an_error():
    with pytest.raises(Exception):
        parse_verdict("not json", 1)