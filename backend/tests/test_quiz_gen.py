from backend.app.onboarding.quiz_gen import check_questions, shuffle_options

URL, SHA = "https://github.com/x/y", "abc123"
SOURCES = [
    {"path": "a.py", "start": 10, "end": 30, "kind": "function", "symbol": "f", "content": ""},
    {"path": "b.py", "start": 100, "end": 150, "kind": "class", "symbol": "B", "content": ""},
]


def _q(source=1, options=("right", "w1", "w2", "w3"), correct=0, lines=(12, 20), question="What does f do?"):
    return {"source": source, "question": question, "options": list(options), "correct": correct,
            "explanation": "because", "lines": {"start": lines[0], "end": lines[1]}}


def test_valid_question_kept_with_pinned_link():
    qs, checks = check_questions(SOURCES, {"questions": [_q()]}, URL, SHA)
    q = qs[0]
    assert q["id"] == "q1" and q["path"] == "a.py"
    assert q["options"][q["correct"]] == "right"        # correct index follows the shuffle
    assert SHA in q["url"] and q["url"].endswith("#L12-L20")
    assert checks["kept"] == 1 and checks["dropped"] == {} and checks["missing_sources"] == 1


def test_bad_questions_dropped_and_counted_by_reason():
    bad = [
        _q(options=("a", "b", "c")),                 # 3 options
        _q(options=("A", "a", "b", "c")),            # duplicate (case-insensitive)
        _q(options=("a", "", "b", "c")),             # empty option
        _q(correct=4),                               # bad correct index
        _q(lines=(5, 12)),                           # starts before the chunk (line 10)
        _q(source=3),                                # no such source
        _q(question="   "),                          # empty question
    ]
    qs, checks = check_questions(SOURCES, {"questions": bad}, URL, SHA)
    assert qs == []
    assert checks["dropped"] == {"bad_options": 3, "bad_correct": 1, "bad_lines": 1,
                                 "unknown_source": 1, "empty_question": 1}
    assert checks["missing_sources"] == 2


def test_second_question_for_same_source_dropped():
    qs, checks = check_questions(SOURCES, {"questions": [_q(), _q(question="Another?")]}, URL, SHA)
    assert len(qs) == 1 and checks["dropped"] == {"duplicate_source": 1}


def test_invalid_first_try_does_not_block_a_valid_second():
    qs, checks = check_questions(SOURCES, {"questions": [_q(correct=9), _q()]}, URL, SHA)
    assert len(qs) == 1 and checks["dropped"] == {"bad_correct": 1}


def test_shuffle_is_repeatable_and_keeps_the_answer():
    opts = ["right", "w1", "w2", "w3"]
    a = shuffle_options(opts, 0, seed="a.py:10:What does f do?")
    b = shuffle_options(opts, 0, seed="a.py:10:What does f do?")
    assert a == b                                        # same seed -> same order
    shuffled, correct = a
    assert shuffled[correct] == "right" and sorted(shuffled) == sorted(opts)