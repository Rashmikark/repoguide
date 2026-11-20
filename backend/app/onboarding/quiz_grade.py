"""What the browser may see, and grading on the server.
public_view strips everything that reveals an answer - including checks.correct_positions,
which IS the answer key. grade() compares submitted answers with the stored quiz."""

QUIZ_BY_ID_SQL = "SELECT id, quiz FROM onboarding_quizzes WHERE id = %s"


def load_quiz_by_id(conn, quiz_id: int) -> dict | None:
    row = conn.execute(QUIZ_BY_ID_SQL, (quiz_id,)).fetchone()
    return None if row is None else {**row[1], "quiz_id": row[0]}


def public_view(quiz: dict) -> dict:
    return {
        "quiz_id": quiz.get("quiz_id"),
        "cached": quiz.get("cached"),
        "questions": [{"id": q["id"], "question": q["question"], "options": q["options"],
                       "path": q["path"], "symbol": q["symbol"]} for q in quiz.get("questions", [])],
    }


def grade(quiz: dict, answers: dict[str, int]) -> dict:
    ids = [q["id"] for q in quiz.get("questions", [])]
    results, score = [], 0
    for q in quiz.get("questions", []):
        given = answers.get(q["id"])
        ok = given == q["correct"]
        score += ok
        results.append({
            "id": q["id"], "your_answer": given, "correct_answer": q["correct"],
            "is_correct": ok, "explanation": q["explanation"],
            "proof": {"path": q["path"], "start": q["start"], "end": q["end"], "url": q["url"]},
        })
    return {"quiz_id": quiz.get("quiz_id"), "score": score, "total": len(ids),
            "results": results,
            "unanswered": [i for i in ids if i not in answers],
            "unknown_ids": sorted(set(answers) - set(ids))}