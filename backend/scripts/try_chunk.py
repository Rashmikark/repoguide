import sys
from collections import Counter

from backend.app.ingest.chunker import chunk_file
from backend.app.ingest.repo_loader import load_repo

repo = load_repo(sys.argv[1])
chunks, missed = [], 0

for f in repo.files:
    file_chunks = chunk_file(f)
    chunks.extend(file_chunks)
    covered = set()
    for c in file_chunks:
        covered.update(range(c.start_line, c.end_line + 1))
    for i, line in enumerate(f.text.split("\n"), start=1):
        if line.strip() and i not in covered:
            missed += 1

sizes = [c.end_line - c.start_line + 1 for c in chunks]
print(f"{repo.owner}/{repo.name}: {len(repo.files)} files -> {len(chunks)} chunks")
print("by kind:", dict(Counter(c.kind for c in chunks)))
print("lines per chunk: max", max(sizes), "| avg", round(sum(sizes) / len(sizes), 1))
print("non-blank lines missed:", missed)

samples = ([c for c in chunks if c.kind == "function"][:1]
           + [c for c in chunks if c.kind == "class"][:1]
           + [c for c in chunks if c.kind == "test"][:1])


print("\nmodule chunks by top folder:")
module_dirs = Counter(c.path.split("/")[0] for c in chunks if c.kind == "module")
for folder, n in module_dirs.most_common(5):
    print(f"  {n:>4}  {folder}")

big = sorted((c for c in chunks if c.kind == "module"), key=lambda c: c.start_line - c.end_line)[:3]
for c in big:
    print(f"\n--- biggest module: {c.path} L{c.start_line}-{c.end_line}")
    print("\n".join(c.content.split("\n")[:4]))