from backend.app.onboarding.path_explain import max_focus_width, merge

PLAN = {"days": [
    {"day": 1, "minutes": 10, "over_budget": False, "items": [
        {"path": "README.md", "group": "readme", "lines": 50, "minutes": 5, "skim": False},   # max width 25
        {"path": "src/a.py", "group": "core", "lines": 100, "minutes": 5, "skim": False},    # max width 50
    ]},
]}
ZERO = {"unknown_days": [], "unknown_paths": [], "missing_files": 0, "invalid_focus": 0, "wide_focus": 0}


def _file(path, look="x", focus=((1, 10),)):
    return {"path": path, "look_for": look, "focus": [{"start": s, "end": e} for s, e in focus]}


def test_good_answer_is_attached():
    data = {"days": [{"day": 1, "goal": "Learn the API", "files": [
        _file("README.md", "intro", [(1, 20)]), _file("src/a.py", "core", [(5, 30), (40, 60)])]}]}
    days, checks = merge(PLAN, data)
    assert days[0]["goal"] == "Learn the API"
    assert days[0]["items"][1]["focus"] == [{"start": 5, "end": 30}, {"start": 40, "end": 60}]
    assert checks == ZERO


def test_invented_path_dropped_and_forgotten_file_kept():
    data = {"days": [{"day": 1, "goal": "g", "files": [
        _file("README.md"), _file("src/made_up.py")]}]}
    days, checks = merge(PLAN, data)
    assert [it["path"] for it in days[0]["items"]] == ["README.md", "src/a.py"]   # plan unchanged
    assert days[0]["items"][1]["look_for"] == ""
    assert checks["unknown_paths"] == ["src/made_up.py"] and checks["missing_files"] == 1


def test_bad_and_extra_focus_ranges_dropped():
    data = {"days": [{"day": 1, "goal": "g", "files": [
        _file("README.md", focus=[(40, 60)]),                         # past line 50 -> invalid
        _file("src/a.py", focus=[(1, 2), (3, 4), (5, 6), (7, 8)])]}]}  # 4th is over the limit
    days, checks = merge(PLAN, data)
    assert days[0]["items"][0]["focus"] == []
    assert len(days[0]["items"][1]["focus"]) == 3
    assert checks["invalid_focus"] == 2


def test_wide_focus_dropped_and_counted():
    data = {"days": [{"day": 1, "goal": "g", "files": [
        _file("README.md", focus=[(1, 50)]),                 # whole file: 50 > 25
        _file("src/a.py", focus=[(1, 50), (1, 51)])]}]}      # 50 ok, 51 > 50
    days, checks = merge(PLAN, data)
    assert days[0]["items"][0]["focus"] == []
    assert days[0]["items"][1]["focus"] == [{"start": 1, "end": 50}]
    assert checks["wide_focus"] == 2
    assert max_focus_width(9) == 5 and max_focus_width(1376) == 120


def test_missing_day_and_unknown_day():
    days, checks = merge(PLAN, {"days": [{"day": 7, "goal": "ghost", "files": []}]})
    assert days[0]["goal"] == "" and checks["unknown_days"] == [7]
    assert checks["missing_files"] == 2