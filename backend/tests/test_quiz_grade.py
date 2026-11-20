from backend.app.onboarding.quiz_grade import grade, public_view

QUIZ = {
    "quiz_id": 7, "cached": True,
    "checks": {"kept": 2, "correct_positions": [2, 0]},
    "questions": [
        {"id": "q1", "question": "Q one?", "options": ["a", "b", "c", "d"], "correct": 2,
         "explanation": "because c", "path": "a.py", "symbol": "f", "start": 1, "end": 5, "url": "u1"},
        {"id": "q2", "question": "Q two?", "options": ["e", "f", "g", "h"], "correct": 0,
         "explanation": "because e", "path": "b.py", "symbol": "g", "start": 9, "end": 12, "url": "u2"},
    ],
}


def test_public_view_reveals_nothing_about_answers():
    view = public_view(QUIZ)
    text = str(view)
    assert "checks" not in view and "correct_positions" not in text      # the answer key list
    for q in view["questions"]:
        assert set(q) == {"id", "question", "options", "path", "symbol"}
    assert "because" not in text and "u1" not in text                     # explanation and proof
    assert view["quiz_id"] == 7 and len(view["questions"]) == 2


def test_grade_scores_and_returns_explanations():
    out = grade(QUIZ, {"q1": 2, "q2": 3})
    assert out["score"] == 1 and out["total"] == 2
    assert [r["is_correct"] for r in out["results"]] == [True, False]
    assert out["results"][1]["correct_answer"] == 0
    assert out["results"][1]["proof"]["url"] == "u2"
    assert out["unanswered"] == [] and out["unknown_ids"] == []


def test_unanswered_is_wrong_and_unknown_ids_ignored():
    out = grade(QUIZ, {"q1": 2, "q9": 1})
    assert out["score"] == 1
    assert out["unanswered"] == ["q2"] and out["unknown_ids"] == ["q9"]
    assert out["results"][1]["your_answer"] is None