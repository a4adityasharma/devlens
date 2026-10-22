from pathlib import Path

from app.analyzer.ast_extractor import extract_symbols_from_file

FIXTURES = Path(__file__).parent / "fixtures"


def _by_type(symbols, type_):
    return [s for s in symbols if s.type == type_]


def test_python_extraction():
    symbols = extract_symbols_from_file(FIXTURES / "sample.py")

    classes = _by_type(symbols, "class")
    methods = _by_type(symbols, "method")
    functions = _by_type(symbols, "function")
    imports = _by_type(symbols, "import")

    assert [c.name for c in classes] == ["UserService"]
    assert {m.name for m in methods} == {"authenticate", "validate", "logout"}
    assert all(m.parent == "UserService" for m in methods)
    assert {f.name for f in functions} == {"generate_token", "top_level_helper"}
    helper = next(f for f in functions if f.name == "top_level_helper")
    assert helper.parameters == ["a", "b", "*args", "**kwargs"]
    assert {i.name for i in imports} == {"os", "typing"}


def test_python_call_extraction():
    symbols = extract_symbols_from_file(FIXTURES / "sample.py")
    calls = _by_type(symbols, "call")
    calls_by_callee = {c.name: c for c in calls}

    # generate_token(username) called from inside UserService.authenticate,
    # as a bare (no-receiver) call.
    assert calls_by_callee["generate_token"].caller == "UserService.authenticate"
    assert calls_by_callee["generate_token"].receiver is None

    # self.validate(token) called from inside UserService.authenticate.
    assert calls_by_callee["validate"].caller == "UserService.authenticate"
    assert calls_by_callee["validate"].receiver == "self"

    # svc.authenticate(...) called from top_level_helper.
    assert calls_by_callee["authenticate"].caller == "top_level_helper"
    assert calls_by_callee["authenticate"].receiver == "svc"


def test_javascript_extraction():
    symbols = extract_symbols_from_file(FIXTURES / "sample.js")

    classes = _by_type(symbols, "class")
    methods = _by_type(symbols, "method")
    functions = _by_type(symbols, "function")

    assert [c.name for c in classes] == ["AuthService"]
    assert {m.name for m in methods} == {"login", "validate"}
    login = next(m for m in methods if m.name == "login")
    assert login.parameters == ["username", "password"]
    # `function` declaration + two `const x = () => {}` / named fns
    assert {f.name for f in functions} == {"generateToken", "refreshToken", "logout"}


def test_javascript_call_extraction():
    symbols = extract_symbols_from_file(FIXTURES / "sample.js")
    calls = _by_type(symbols, "call")
    calls_by_callee = {c.name: c for c in calls}

    # generateToken(username) called from inside AuthService.login — this is
    # the case that was previously (silently) dropped because it's the
    # value of a `const token = ...` declarator, not a function assignment.
    assert calls_by_callee["generateToken"].caller == "AuthService.login"
    assert calls_by_callee["generateToken"].receiver is None

    # this.validate(token) called from inside AuthService.login.
    assert calls_by_callee["validate"].caller == "AuthService.login"
    assert calls_by_callee["validate"].receiver == "this"

    # svc.login("a", "b") called from inside the `logout` arrow function.
    assert calls_by_callee["login"].caller == "logout"
    assert calls_by_callee["login"].receiver == "svc"


def test_typescript_extraction():
    symbols = extract_symbols_from_file(FIXTURES / "sample.ts")

    classes = _by_type(symbols, "class")
    methods = _by_type(symbols, "method")
    functions = _by_type(symbols, "function")

    assert [c.name for c in classes] == ["TokenValidator"]
    assert {m.name for m in methods} == {"validate", "checkFormat"}
    validate = next(m for m in methods if m.name == "validate")
    assert validate.parameters == ["token", "strict"]
    assert [f.name for f in functions] == ["verifyRequest"]


def test_typescript_call_extraction():
    symbols = extract_symbols_from_file(FIXTURES / "sample.ts")
    calls = _by_type(symbols, "call")
    calls_by_callee = {c.name: c for c in calls}

    assert calls_by_callee["checkFormat"].caller == "TokenValidator.validate"
    assert calls_by_callee["checkFormat"].receiver == "this"

    assert calls_by_callee["validate"].caller == "verifyRequest"
    assert calls_by_callee["validate"].receiver == "validator"


def test_unsupported_extension_returns_empty():
    symbols = extract_symbols_from_file(FIXTURES / "sample.py")
    assert isinstance(symbols, list)
    fake = FIXTURES / "does_not_exist.rb"
    assert extract_symbols_from_file(fake) == []
