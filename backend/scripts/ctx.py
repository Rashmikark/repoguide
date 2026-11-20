"""Print every line containing TEXT, with surrounding lines and line numbers.
Usage:
    python -m backend.scripts.ctx <file or folder> "<text>" [lines_around]
Example:
    python -m backend.scripts.ctx data\\repos\\pallets__itsdangerous\\src "does not match" 4
"""
import sys
from pathlib import Path

EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".md", ".rst"}


def main() -> None:
    target, text = Path(sys.argv[1]), sys.argv[2]
    around = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    files = [target] if target.is_file() else sorted(
        p for p in target.rglob("*") if p.is_file() and p.suffix in EXTENSIONS
    )
    for path in files:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        for i, line in enumerate(lines, start=1):
            if text in line:
                print(f"\n=== {path.as_posix()} : line {i}")
                for j in range(max(1, i - around), min(len(lines), i + around) + 1):
                    marker = ">>" if j == i else "  "
                    print(f"{marker}{j:>5}| {lines[j - 1]}")


if __name__ == "__main__":
    main()