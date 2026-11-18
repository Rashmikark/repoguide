from dataclasses import dataclass

import tree_sitter_javascript as tsjs
import tree_sitter_python as tspy
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

from backend.app.ingest.repo_loader import SourceFile

MAX_LINES = 120
WINDOW_OVERLAP = 10

PARSERS = {
    "python": Parser(Language(tspy.language())),
    "javascript": Parser(Language(tsjs.language())),
    # The TSX grammar also parses plain .ts files (rare edge cases aside).
    "typescript": Parser(Language(tsts.language_tsx())),
}

DEF_KINDS = {
    "function_definition": "function",          # python
    "class_definition": "class",                # python
    "function_declaration": "function",         # js/ts
    "generator_function_declaration": "function",
    "class_declaration": "class",
    "abstract_class_declaration": "class",
    "interface_declaration": "type",            # ts
    "type_alias_declaration": "type",
    "enum_declaration": "type",
}
FUNCTION_VALUES = {"arrow_function", "function_expression", "function"}


@dataclass
class Chunk:
    path: str
    start_line: int     # 1-based, inclusive
    end_line: int       # 1-based, inclusive
    kind: str           # function | class | type | module | doc
    symbol: str | None
    content: str


def chunk_file(f: SourceFile) -> list[Chunk]:
    # split("\n") matches how tree-sitter counts rows; splitlines() does not.
    lines = f.text.split("\n")
    if f.language in PARSERS:
        chunks = _chunk_code(f, lines)
    else:
        chunks = _chunk_doc(f, lines)
    return [c for c in chunks if c.content.strip()]


# ---------- helpers ----------

def _emit(out, f, lines, start, end, kind, symbol):
    """Add one chunk, or several overlapping windows if it is too long."""
    end = min(end, len(lines))
    s = start
    while s <= end:
        e = min(s + MAX_LINES - 1, end)
        content = "\n".join(lines[s - 1:e])
        out.append(Chunk(f.path, s, e, kind, symbol, content))
        if e == end:
            break
        s += MAX_LINES - WINDOW_OVERLAP


def _name(node):
    n = node.child_by_field_name("name")
    return n.text.decode("utf-8") if n is not None else None


def _unwrap(node):
    """Return (definition, outer). Decorators and `export` stay in the chunk."""
    if node.type == "decorated_definition":
        return node.child_by_field_name("definition"), node
    if node.type == "export_statement":
        inner = node.child_by_field_name("declaration")
        if inner is not None:
            return inner, node
    return node, node


def _arrow_function_name(node):
    """`const fetchUser = () => {...}` counts as a function."""
    if node.type not in ("lexical_declaration", "variable_declaration"):
        return None
    for d in node.named_children:
        if d.type == "variable_declarator":
            value = d.child_by_field_name("value")
            if value is not None and value.type in FUNCTION_VALUES:
                return _name(d)
    return None

TEST_CALLEES = {"test", "it", "describe", "suite", "bench"}


def _call_block(node):
    """`test('retries on 500', async t => {...})` becomes its own chunk."""
    if node.type != "expression_statement" or not node.named_children:
        return None, None
    call = node.named_children[0]
    if call.type != "call_expression":
        return None, None
    args = call.child_by_field_name("arguments")
    if args is None or not any(a.type in FUNCTION_VALUES for a in args.named_children):
        return None, None

    callee = call.child_by_field_name("function").text.decode("utf-8")
    title = next(
        (a.text.decode("utf-8")[1:-1] for a in args.named_children
         if a.type in ("string", "template_string")),
        None,
    )
    kind = "test" if callee.split(".")[0] in TEST_CALLEES else "module"
    return kind, title or callee
# ---------- code ----------

def _chunk_code(f, lines):
    tree = PARSERS[f.language].parse(f.text.encode("utf-8"))
    out = []
    gap_start = 1   # first line not yet covered by a chunk

    for node in tree.root_node.named_children:
        defn, outer = _unwrap(node)
        kind = DEF_KINDS.get(defn.type)
        symbol = _name(defn) if kind else None
        if kind is None:
            symbol = _arrow_function_name(defn)
            kind = "function" if symbol else None
        if kind is None:
            kind, symbol = _call_block(defn)
        if kind is None:
            continue    # imports, constants etc. stay in the module gap

        start = outer.start_point[0] + 1
        end = outer.end_point[0] + 1
        if gap_start < start:
            _emit(out, f, lines, gap_start, start - 1, "module", None)

        if kind == "class" and end - start + 1 > MAX_LINES:
            _chunk_big_class(out, f, lines, defn, start, end, symbol)
        else:
            _emit(out, f, lines, start, end, kind, symbol)
        gap_start = end + 1

    if gap_start <= len(lines):
        _emit(out, f, lines, gap_start, len(lines), "module", None)
    return out


def _chunk_big_class(out, f, lines, defn, start, end, class_name):
    body = defn.child_by_field_name("body")
    methods = []
    for child in (body.named_children if body is not None else []):
        inner, outer = _unwrap(child)
        if inner.type in ("function_definition", "method_definition"):
            methods.append((outer.start_point[0] + 1, outer.end_point[0] + 1, _name(inner)))

    if not methods:
        _emit(out, f, lines, start, end, "class", class_name)
        return

    cursor = start
    for m_start, m_end, m_name in methods:
        if cursor < m_start:
            _emit(out, f, lines, cursor, m_start - 1, "class", class_name)
        _emit(out, f, lines, m_start, m_end, "function", f"{class_name}.{m_name}")
        cursor = m_end + 1
    if cursor <= end:
        _emit(out, f, lines, cursor, end, "class", class_name)


# ---------- docs ----------

def _chunk_doc(f, lines):
    heads, in_fence = [], False
    if f.language == "markdown":
        for i, line in enumerate(lines, start=1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
            elif not in_fence and line.startswith("#"):
                heads.append(i)

    bounds = sorted(set([1] + heads))
    out = []
    for i, s in enumerate(bounds):
        e = bounds[i + 1] - 1 if i + 1 < len(bounds) else len(lines)
        title = lines[s - 1].lstrip("#").strip() if s in heads else None
        _emit(out, f, lines, s, e, "doc", title)
    return out