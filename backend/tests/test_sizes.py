from backend.app.onboarding.sizes import load_sizes


class FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return self

    def fetchall(self):
        return self.rows


def test_load_sizes_maps_rows_and_keeps_empty_files():
    conn = FakeConn([("README.md", 50), ("src/pkg/__init__.py", 0)])
    assert load_sizes(conn, 7) == {"README.md": 50, "src/pkg/__init__.py": 0}
    sql, params = conn.calls[0]
    assert params == (7,)
    assert "LEFT JOIN" in sql      # files with no chunks must not disappear