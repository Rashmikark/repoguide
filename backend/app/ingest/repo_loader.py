import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path("data/repos")
MAX_FILES = 1500
MAX_FILE_BYTES = 200_000

LANGUAGES = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".md": "markdown", ".rst": "rst",
}
SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "__pycache__",
    ".venv", "venv", ".tox", ".next", "coverage", "site-packages",
}
SKIP_SUFFIXES = (".min.js", ".bundle.js")

GITHUB_URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")

# Never let git open a login prompt: a private/missing repo must fail fast,
# not freeze the server waiting for a password.
_GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}

# What git prints when a repo is missing or private (GitHub answers both the same way).
_NOT_FOUND_HINTS = (
    "repository not found",
    "could not read username",
    "terminal prompts disabled",
    "user interactivity has been disabled",
    "authentication failed",
)


class RepoNotFound(Exception):
    """The repo does not exist or is private."""


class GitHubUnavailable(Exception):
    """GitHub could not be reached (network error, timeout, outage)."""


@dataclass
class SourceFile:
    path: str          # relative, with forward slashes: "src/app/main.py"
    language: str
    size_bytes: int
    text: str


@dataclass
class LoadedRepo:
    owner: str
    name: str
    commit_sha: str
    files: list[SourceFile]
    skipped: dict[str, int]


def parse_github_url(url: str) -> tuple[str, str]:
    match = GITHUB_URL.match(url.strip())
    if not match:
        raise ValueError(f"Not a public GitHub repo URL: {url!r}")
    return match.group(1), match.group(2)


def _force_remove(func, path, _exc_info):
    Path(path).chmod(stat.S_IWRITE)   # Windows: .git files are read-only
    func(path)


def clone(owner: str, name: str) -> Path:
    dest = DATA_DIR / f"{owner}__{name}"
    if dest.exists():
        shutil.rmtree(dest, onerror=_force_remove)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{owner}/{name}.git"
    subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", url, str(dest)],
        check=True, timeout=300, env=_GIT_ENV,
    )
    return dest


def collect_files(root: Path) -> tuple[list[SourceFile], dict[str, int]]:
    files: list[SourceFile] = []
    skipped = {"ignored_dir": 0, "extension": 0, "too_large": 0, "not_text": 0}

    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            skipped["ignored_dir"] += 1
            continue
        language = LANGUAGES.get(p.suffix.lower())
        if language is None or p.name.endswith(SKIP_SUFFIXES):
            skipped["extension"] += 1
            continue
        size = p.stat().st_size
        if size > MAX_FILE_BYTES:
            skipped["too_large"] += 1
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skipped["not_text"] += 1
            continue
        files.append(SourceFile(rel.as_posix(), language, size, text))

    if len(files) > MAX_FILES:
        raise ValueError(f"Repo too large: {len(files)} files (limit {MAX_FILES})")
    return files, skipped


def load_repo(url: str) -> LoadedRepo:
    owner, name = parse_github_url(url)
    root = clone(owner, name)
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, env=_GIT_ENV,
    ).stdout.strip()
    files, skipped = collect_files(root)
    return LoadedRepo(owner, name, sha, files, skipped)


def classify_ls_remote(returncode: int, stdout: str, stderr: str) -> str | None:
    """Turn a `git ls-remote` result into a commit SHA, None (empty repo), or an error."""
    if returncode == 0:
        return stdout.split()[0] if stdout.strip() else None
    message = stderr.strip()
    if any(hint in message.lower() for hint in _NOT_FOUND_HINTS):
        raise RepoNotFound(message)
    raise GitHubUnavailable(message or f"git exited with code {returncode}")


def remote_head_sha(owner: str, name: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "ls-remote", f"https://github.com/{owner}/{name}.git", "HEAD"],
            capture_output=True, text=True, timeout=60, env=_GIT_ENV,
        )
    except subprocess.TimeoutExpired:
        raise GitHubUnavailable("git ls-remote timed out after 60s")
    return classify_ls_remote(result.returncode, result.stdout, result.stderr)