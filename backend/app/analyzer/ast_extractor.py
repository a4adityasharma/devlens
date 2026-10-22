"""
AST Extraction (architecture doc §7).

Walks a Tree-sitter parse tree and produces a language-agnostic list of
symbols:

    {
        "type": "function" | "class" | "method" | "import" | "call",
        "name": str,                # for "call": the callee name (e.g. "login")
        "file": str,
        "line_start": int,
        "line_end": int,
        "parameters": [str, ...],   # functions/methods only
        "parent": str | None,       # class name, for methods
        "source": str | None,       # import target, for imports
        "caller": str | None,       # for "call": qualified name of the
                                     # enclosing function/method, e.g.
                                     # "AuthService.login" or "top_level"
        "receiver": str | None,     # for "call": the object expression the
                                     # method was called on, e.g. "self" in
                                     # `self.validate(...)`; None for a bare
                                     # `generate_token(...)` call
    }

This is the "common internal representation" the rest of the system
(Neo4j relationship extraction, Qdrant chunking) is built on, so it
should not care whether the original file was Python or TypeScript.

NOTE on "call" symbols: callee names are NOT resolved to a specific
definition here — `svc.login(...)` just records callee_name="login",
receiver="svc". Resolving that to a specific Method node (there may be
several `login` methods across the repo) is the graph builder's job
(Phase 4 / app/knowledge/graph_builder.py) and is a deliberately simple
name-based match for the MVP, not full type-aware resolution.
"""
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from app.analyzer.parser import ParsedFile, get_parser_pool


@dataclass
class Symbol:
    type: str  # function | class | method | import | call
    name: str
    file: str
    line_start: int
    line_end: int
    parameters: list[str] = field(default_factory=list)
    parent: str | None = None
    source: str | None = None  # import module/path
    caller: str | None = None  # call: enclosing function/method (qualified)
    receiver: str | None = None  # call: object expression, if any

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "name": self.name,
            "file": self.file,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "parameters": self.parameters,
            "parent": self.parent,
            "source": self.source,
            "caller": self.caller,
            "receiver": self.receiver,
        }


def _text(node: Node | None, source: bytes) -> str | None:
    if node is None:
        return None
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _line_range(node: Node) -> tuple[int, int]:
    # Tree-sitter rows are 0-indexed; report 1-indexed lines like an editor.
    return node.start_point[0] + 1, node.end_point[0] + 1


def _qualify(parent_class: str | None, name: str | None) -> str | None:
    if name is None:
        return None
    return f"{parent_class}.{name}" if parent_class else name


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

def _python_params(params_node: Node | None, source: bytes) -> list[str]:
    if params_node is None:
        return []
    names = []
    for child in params_node.named_children:
        if child.type == "identifier":
            names.append(_text(child, source))
        elif child.type in ("default_parameter", "typed_parameter", "typed_default_parameter"):
            name_node = child.child_by_field_name("name") or child.named_children[0]
            names.append(_text(name_node, source))
        elif child.type in ("list_splat_pattern", "dictionary_splat_pattern"):
            names.append(_text(child, source))
    return [n for n in names if n]


def _python_call_target(func_node: Node | None, source: bytes) -> tuple[str | None, str | None]:
    """Returns (callee_name, receiver) for a Python `call` node's `function` field."""
    if func_node is None:
        return None, None
    if func_node.type == "attribute":
        obj = func_node.child_by_field_name("object")
        attr = func_node.child_by_field_name("attribute")
        return _text(attr, source), _text(obj, source)
    if func_node.type == "identifier":
        return _text(func_node, source), None
    # Chained/subscripted calls etc. — fall back to raw source text so we
    # still record *something* rather than silently dropping the call.
    return _text(func_node, source), None


def _walk_python(
    node: Node, source: bytes, file_path: str, symbols: list[Symbol],
    parent_class: str | None = None, current_function: str | None = None,
):
    for child in node.named_children:
        if child.type == "class_definition":
            name = _text(child.child_by_field_name("name"), source)
            start, end = _line_range(child)
            symbols.append(Symbol(type="class", name=name, file=file_path, line_start=start, line_end=end))
            body = child.child_by_field_name("body")
            if body is not None:
                _walk_python(body, source, file_path, symbols, parent_class=name, current_function=current_function)

        elif child.type == "function_definition":
            name = _text(child.child_by_field_name("name"), source)
            start, end = _line_range(child)
            params = _python_params(child.child_by_field_name("parameters"), source)
            symbols.append(Symbol(
                type="method" if parent_class else "function",
                name=name, file=file_path, line_start=start, line_end=end,
                parameters=params, parent=parent_class,
            ))
            body = child.child_by_field_name("body")
            if body is not None:
                qualified = _qualify(parent_class, name)
                _walk_python(body, source, file_path, symbols, parent_class=parent_class, current_function=qualified)

        elif child.type == "import_statement":
            for name_node in child.named_children:
                mod = _text(name_node, source)
                if mod:
                    start, end = _line_range(child)
                    symbols.append(Symbol(type="import", name=mod, file=file_path,
                                           line_start=start, line_end=end, source=mod))

        elif child.type == "import_from_statement":
            module_node = child.child_by_field_name("module_name")
            mod = _text(module_node, source)
            start, end = _line_range(child)
            symbols.append(Symbol(type="import", name=mod or "?", file=file_path,
                                   line_start=start, line_end=end, source=mod))

        elif child.type == "call":
            func_node = child.child_by_field_name("function")
            callee_name, receiver = _python_call_target(func_node, source)
            start, end = _line_range(child)
            if callee_name:
                symbols.append(Symbol(
                    type="call", name=callee_name, file=file_path,
                    line_start=start, line_end=end, parent=parent_class,
                    caller=current_function, receiver=receiver,
                ))
            # Recurse into arguments etc. so calls-within-calls are found,
            # e.g. `outer(inner(x))`.
            _walk_python(child, source, file_path, symbols, parent_class=parent_class, current_function=current_function)

        else:
            _walk_python(child, source, file_path, symbols, parent_class=parent_class, current_function=current_function)


# ---------------------------------------------------------------------------
# JavaScript / TypeScript
# ---------------------------------------------------------------------------

def _js_params(params_node: Node | None, source: bytes) -> list[str]:
    if params_node is None:
        return []
    names = []
    for child in params_node.named_children:
        if child.type == "identifier":
            names.append(_text(child, source))
        elif child.type in ("required_parameter", "optional_parameter"):
            # TypeScript typed parameters
            pattern = child.child_by_field_name("pattern")
            names.append(_text(pattern, source))
        elif child.type == "assignment_pattern":
            left = child.child_by_field_name("left")
            names.append(_text(left, source))
        elif child.type in ("rest_pattern",):
            names.append(_text(child, source))
        elif child.type == "object_pattern":
            names.append(_text(child, source))
    return [n for n in names if n]


def _js_call_target(func_node: Node | None, source: bytes) -> tuple[str | None, str | None]:
    """Returns (callee_name, receiver) for a JS/TS `call_expression`'s `function` field."""
    if func_node is None:
        return None, None
    if func_node.type == "member_expression":
        obj = func_node.child_by_field_name("object")
        prop = func_node.child_by_field_name("property")
        return _text(prop, source), _text(obj, source)
    if func_node.type == "identifier":
        return _text(func_node, source), None
    return _text(func_node, source), None


def _walk_js(
    node: Node, source: bytes, file_path: str, symbols: list[Symbol],
    parent_class: str | None = None, current_function: str | None = None,
):
    for child in node.named_children:
        if child.type == "class_declaration":
            name = _text(child.child_by_field_name("name"), source)
            start, end = _line_range(child)
            symbols.append(Symbol(type="class", name=name, file=file_path, line_start=start, line_end=end))
            body = child.child_by_field_name("body")
            if body is not None:
                _walk_js(body, source, file_path, symbols, parent_class=name, current_function=current_function)

        elif child.type == "method_definition":
            name_node = child.child_by_field_name("name")
            name = _text(name_node, source)
            start, end = _line_range(child)
            params = _js_params(child.child_by_field_name("parameters"), source)
            symbols.append(Symbol(
                type="method", name=name, file=file_path, line_start=start, line_end=end,
                parameters=params, parent=parent_class,
            ))
            body = child.child_by_field_name("body")
            if body is not None:
                qualified = _qualify(parent_class, name)
                _walk_js(body, source, file_path, symbols, parent_class=parent_class, current_function=qualified)

        elif child.type == "function_declaration":
            name = _text(child.child_by_field_name("name"), source)
            start, end = _line_range(child)
            params = _js_params(child.child_by_field_name("parameters"), source)
            symbols.append(Symbol(
                type="function", name=name, file=file_path, line_start=start, line_end=end,
                parameters=params, parent=parent_class,
            ))
            body = child.child_by_field_name("body")
            if body is not None:
                _walk_js(body, source, file_path, symbols, parent_class=parent_class, current_function=name)

        elif child.type in ("lexical_declaration", "variable_declaration"):
            # const foo = (a, b) => {...}  /  const foo = function(a, b) {...}
            # const bar = someCall(x)      <- still need to find calls in here
            for decl in child.named_children:
                if decl.type != "variable_declarator":
                    continue
                value = decl.child_by_field_name("value")
                if value is not None and value.type in ("arrow_function", "function", "function_expression"):
                    name = _text(decl.child_by_field_name("name"), source)
                    start, end = _line_range(child)
                    params = _js_params(value.child_by_field_name("parameters"), source)
                    symbols.append(Symbol(
                        type="function", name=name, file=file_path, line_start=start, line_end=end,
                        parameters=params, parent=parent_class,
                    ))
                    body = value.child_by_field_name("body")
                    if body is not None:
                        _walk_js(body, source, file_path, symbols, parent_class=parent_class, current_function=name)
                elif value is not None:
                    # Not a function assignment (e.g. `const token = generateToken(x)`
                    # or `const svc = new AuthService()`) — walk the declarator
                    # itself (not just `value`) so a call_expression sitting
                    # directly as the value is still matched by the dispatch
                    # below, not skipped past.
                    _walk_js(decl, source, file_path, symbols, parent_class=parent_class, current_function=current_function)

        elif child.type == "import_statement":
            source_node = child.child_by_field_name("source")
            mod = _text(source_node, source)
            if mod:
                mod = mod.strip("\"'")
            start, end = _line_range(child)
            symbols.append(Symbol(type="import", name=mod or "?", file=file_path,
                                   line_start=start, line_end=end, source=mod))

        elif child.type == "call_expression":
            func_node = child.child_by_field_name("function")
            callee_name, receiver = _js_call_target(func_node, source)
            start, end = _line_range(child)
            if callee_name:
                symbols.append(Symbol(
                    type="call", name=callee_name, file=file_path,
                    line_start=start, line_end=end, parent=parent_class,
                    caller=current_function, receiver=receiver,
                ))
            _walk_js(child, source, file_path, symbols, parent_class=parent_class, current_function=current_function)

        else:
            _walk_js(child, source, file_path, symbols, parent_class=parent_class, current_function=current_function)


_WALKERS = {
    "python": _walk_python,
    "javascript": _walk_js,
    "typescript": _walk_js,
}


def extract_symbols(parsed: ParsedFile) -> list[Symbol]:
    walker = _WALKERS.get(parsed.language)
    if walker is None:
        return []
    symbols: list[Symbol] = []
    walker(parsed.root_node, parsed.source, parsed.path, symbols)
    return symbols


def extract_symbols_from_file(path: Path) -> list[Symbol]:
    pool = get_parser_pool()
    parsed = pool.parse_file(path)
    if parsed is None:
        return []
    return extract_symbols(parsed)
