"""
Setup script for Curated SWE-bench Lite Benchmark Suite (5 tasks).
Initializes source files and failing reproduction tests in data/benchmarks/swe_bench_lite.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

BENCH_ROOT = Path(__file__).resolve().parent.parent / "data" / "benchmarks" / "swe_bench_lite"

TASKS = [
    {
        "task_id": "swe_01_requests_empty_params",
        "repo": "psf/requests-like",
        "problem_statement": (
            "When encoding URL query parameters using `encode_query_params(params: dict[str, Any])`, "
            "if a value is None, the parameter should be omitted entirely. If a value is empty string (''), "
            "it should be included as 'key='. Currently, encode_query_params serializes None as the literal string "
            "'None' ('key=None'), causing invalid API queries."
        ),
        "files": {
            "src/myurl/__init__.py": "",
            "src/myurl/params.py": '''from __future__ import annotations
from typing import Any
import urllib.parse

def encode_query_params(params: dict[str, Any]) -> str:
    """Encodes dictionary into a URL query string.
    Rules:
    - If value is None, the key should NOT be included.
    - If value is empty string, key should be included as 'key='
    - Multiple values (list or tuple) should emit multiple key=value pairs.
    """
    pairs: list[str] = []
    for key, val in params.items():
        k = urllib.parse.quote_plus(str(key))
        if isinstance(val, (list, tuple)):
            for item in val:
                if item is not None:
                    v = urllib.parse.quote_plus(str(item))
                    pairs.append(f"{k}={v}")
        else:
            v = urllib.parse.quote_plus(str(val))
            pairs.append(f"{k}={v}")
    return "&".join(pairs)
''',
            "tests/__init__.py": "",
            "tests/test_params.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from myurl.params import encode_query_params

def test_regular_params():
    assert encode_query_params({"a": 1, "b": "hello"}) == "a=1&b=hello"

def test_empty_string_param():
    assert encode_query_params({"query": ""}) == "query="

def test_none_param_omitted():
    assert encode_query_params({"query": "search", "flag": None}) == "query=search"

def test_list_params():
    assert encode_query_params({"tag": ["python", "ai"]}) == "tag=python&tag=ai"
''',
        },
    },
    {
        "task_id": "swe_02_flask_case_insensitive_headers",
        "repo": "pallets/flask-like",
        "problem_statement": (
            "In Headers datastructure, get_all(name: str) should return all values matching the header name "
            "in a case-insensitive manner (e.g. get_all('Accept') must match 'accept', 'Accept', 'ACCEPT'). "
            "Currently get_all performs a case-sensitive lookup on stored pairs, dropping matches when casing varies."
        ),
        "files": {
            "src/http_headers/__init__.py": "",
            "src/http_headers/datastructures.py": '''from __future__ import annotations

class Headers:
    """A case-insensitive multi-dict for HTTP headers."""

    def __init__(self, items: list[tuple[str, str]] | None = None) -> None:
        self._items: list[tuple[str, str]] = list(items or [])

    def add(self, name: str, value: str) -> None:
        self._items.append((name, value))

    def get(self, name: str, default: str | None = None) -> str | None:
        name_lower = name.lower()
        for k, v in self._items:
            if k.lower() == name_lower:
                return v
        return default

    def get_all(self, name: str) -> list[str]:
        return [v for k, v in self._items if k == name]
''',
            "tests/__init__.py": "",
            "tests/test_headers.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from http_headers.datastructures import Headers

def test_case_insensitive_get():
    h = Headers([("Content-Type", "application/json")])
    assert h.get("content-type") == "application/json"

def test_case_insensitive_get_all():
    h = Headers([
        ("Accept", "text/html"),
        ("accept", "application/xhtml+xml"),
        ("ACCEPT", "application/xml"),
        ("Host", "example.com"),
    ])
    results = h.get_all("Accept")
    assert results == ["text/html", "application/xhtml+xml", "application/xml"]
''',
        },
    },
    {
        "task_id": "swe_03_marshmallow_allow_none",
        "repo": "marshmallow-code/marshmallow-like",
        "problem_statement": (
            "In IntegerField.deserialize(value), if allow_none=True and value is None, the field should "
            "return None immediately. Currently, IntegerField.deserialize attempts to call int(value) directly "
            "before checking allow_none, causing a TypeError/ValidationError when None is passed."
        ),
        "files": {
            "src/schema/__init__.py": "",
            "src/schema/fields.py": '''from __future__ import annotations
from typing import Any

class ValidationError(Exception):
    pass

class IntegerField:
    def __init__(self, allow_none: bool = False, min_val: int | None = None) -> None:
        self.allow_none = allow_none
        self.min_val = min_val

    def deserialize(self, value: Any) -> int | None:
        try:
            val = int(value)
        except (ValueError, TypeError) as exc:
            raise ValidationError(f"Invalid integer: {value}") from exc

        if value is None and self.allow_none:
            return None

        if self.min_val is not None and val < self.min_val:
            raise ValidationError(f"Value {val} is below minimum {self.min_val}")
        return val
''',
            "tests/__init__.py": "",
            "tests/test_fields.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from schema.fields import IntegerField, ValidationError

def test_valid_integer():
    f = IntegerField()
    assert f.deserialize("42") == 42

def test_disallow_none():
    f = IntegerField(allow_none=False)
    with pytest.raises(ValidationError):
        f.deserialize(None)

def test_allow_none():
    f = IntegerField(allow_none=True)
    assert f.deserialize(None) is None

def test_min_validation():
    f = IntegerField(min_val=10)
    with pytest.raises(ValidationError):
        f.deserialize(5)
''',
        },
    },
    {
        "task_id": "swe_04_json_depth_limit",
        "repo": "python/serializer",
        "problem_statement": (
            "In SafeJSONEncoder, deeply nested or cyclic data structures cause an unhandled RecursionError. "
            "The encoder should track current recursion depth against max_depth (default 50) and raise "
            "SerializationDepthError when depth > max_depth, preventing process crashes."
        ),
        "files": {
            "src/serializer/__init__.py": "",
            "src/serializer/encoder.py": '''from __future__ import annotations
from typing import Any

class SerializationDepthError(ValueError):
    pass

class SafeJSONEncoder:
    def __init__(self, max_depth: int = 50) -> None:
        self.max_depth = max_depth

    def encode(self, obj: Any) -> Any:
        return self._encode_node(obj, depth=0)

    def _encode_node(self, obj: Any, depth: int) -> Any:
        if isinstance(obj, dict):
            return {str(k): self._encode_node(v, depth + 1) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._encode_node(item, depth + 1) for item in obj]
        if isinstance(obj, (int, float, str, bool)) or obj is None:
            return obj
        return str(obj)
''',
            "tests/__init__.py": "",
            "tests/test_encoder.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from serializer.encoder import SafeJSONEncoder, SerializationDepthError

def test_flat_encode():
    enc = SafeJSONEncoder()
    assert enc.encode({"a": 1, "b": [2, 3]}) == {"a": 1, "b": [2, 3]}

def test_depth_limit_exceeded():
    enc = SafeJSONEncoder(max_depth=5)
    deep: dict = {}
    curr = deep
    for i in range(10):
        curr["next"] = {}
        curr = curr["next"]

    with pytest.raises(SerializationDepthError):
        enc.encode(deep)
''',
        },
    },
    {
        "task_id": "swe_05_semver_prerelease",
        "repo": "semver/semver-like",
        "problem_statement": (
            "In Version comparison, a normal release must have higher precedence than a pre-release version "
            "of the same major.minor.patch (e.g. 1.0.0 is greater than 1.0.0-alpha per SemVer 2.0.0 specification). "
            "Currently, Version.__lt__ compares (self.prerelease or '') < (other.prerelease or ''), which erroneously "
            "ranks 1.0.0 as less than 1.0.0-alpha."
        ),
        "files": {
            "src/semver/__init__.py": "",
            "src/semver/version.py": '''from __future__ import annotations

class Version:
    """Semantic version conforming to SemVer 2.0.0."""

    def __init__(self, major: int, minor: int, patch: int, prerelease: str | None = None) -> None:
        self.major = major
        self.minor = minor
        self.patch = patch
        self.prerelease = prerelease

    @classmethod
    def parse(cls, vstr: str) -> Version:
        parts = vstr.strip().split("-", 1)
        core = parts[0].split(".")
        prerelease = parts[1] if len(parts) > 1 else None
        return cls(int(core[0]), int(core[1]), int(core[2]), prerelease)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return False
        return (self.major, self.minor, self.patch, self.prerelease) == (
            other.major, other.minor, other.patch, other.prerelease
        )

    def __lt__(self, other: Version) -> bool:
        core_self = (self.major, self.minor, self.patch)
        core_other = (other.major, other.minor, other.patch)
        if core_self != core_other:
            return core_self < core_other

        return (self.prerelease or "") < (other.prerelease or "")
''',
            "tests/__init__.py": "",
            "tests/test_version.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from semver.version import Version

def test_core_precedence():
    assert Version.parse("1.0.0") < Version.parse("2.0.0")
    assert Version.parse("1.1.0") < Version.parse("1.2.0")
    assert Version.parse("1.1.1") < Version.parse("1.1.2")

def test_prerelease_lower_than_release():
    v_rel = Version.parse("1.0.0")
    v_pre = Version.parse("1.0.0-alpha")
    assert v_pre < v_rel
    assert not (v_rel < v_pre)

def test_prerelease_ordering():
    assert Version.parse("1.0.0-alpha") < Version.parse("1.0.0-beta")
''',
        },
    },
    {
        "task_id": "swe_06_pytest_mark_precedence",
        "repo": "pytest-dev/pytest-like",
        "problem_statement": (
            "In mark expression evaluation `evaluate_mark_expr(expr: str, marks: set[str]) -> bool`, "
            "`not` must bind tighter than `and`, and `and` must bind tighter than `or`. "
            "Currently, expressions are evaluated strictly left-to-right, causing 'fast and not slow' "
            "to crash with an IndexError or evaluate incorrectly."
        ),
        "files": {
            "src/mark_eval/__init__.py": "",
            "src/mark_eval/evaluator.py": '''from __future__ import annotations

def evaluate_mark_expr(expr: str, marks: set[str]) -> bool:
    """Evaluates a boolean mark expression with boolean precedence (not > and > or)."""
    tokens = expr.strip().split()
    if not tokens:
        return True
    
    val = tokens[0] in marks if tokens[0] != "not" else not (tokens[1] in marks)
    idx = 2 if tokens[0] == "not" else 1
    while idx < len(tokens):
        op = tokens[idx]
        nxt = tokens[idx + 1]
        nxt_val = nxt in marks
        if op == "and":
            val = val and nxt_val
        elif op == "or":
            val = val or nxt_val
        idx += 2
    return val
''',
            "tests/__init__.py": "",
            "tests/test_evaluator.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mark_eval.evaluator import evaluate_mark_expr

def test_simple_mark():
    assert evaluate_mark_expr("unit", {"unit"}) is True
    assert evaluate_mark_expr("integration", {"unit"}) is False

def test_not_precedence():
    assert evaluate_mark_expr("fast and not slow", {"fast"}) is True
    assert evaluate_mark_expr("fast and not slow", {"fast", "slow"}) is False
''',
        },
    },
    {
        "task_id": "swe_07_sympy_poly_quo_rem_zero",
        "repo": "sympy/sympy-like",
        "problem_statement": (
            "In Polynomial.quo_rem(other), dividing a zero polynomial (coefficients all 0 or empty) "
            "by a non-zero polynomial should return (Polynomial([]), Polynomial([])). "
            "Currently, Polynomial.degree() calls max() on an empty list, raising ValueError "
            "when dividing a zero polynomial."
        ),
        "files": {
            "src/algebra/__init__.py": "",
            "src/algebra/poly.py": '''from __future__ import annotations

class Polynomial:
    def __init__(self, coeffs: list[float]) -> None:
        c = list(coeffs)
        while c and c[-1] == 0:
            c.pop()
        self.coeffs = c

    @property
    def degree(self) -> int:
        return max(i for i, c in enumerate(self.coeffs) if c != 0)

    def is_zero(self) -> bool:
        return len(self.coeffs) == 0

    def quo_rem(self, other: Polynomial) -> tuple[Polynomial, Polynomial]:
        if other.is_zero():
            raise ZeroDivisionError("Cannot divide by zero polynomial")
        if self.degree < other.degree:
            return Polynomial([]), Polynomial(self.coeffs)
        quo = [0.0] * (self.degree - other.degree + 1)
        rem = list(self.coeffs)
        for i in range(len(quo) - 1, -1, -1):
            cur_deg = i + other.degree
            if cur_deg < len(rem):
                coeff = rem[cur_deg] / other.coeffs[-1]
                quo[i] = coeff
                for j, c in enumerate(other.coeffs):
                    rem[i + j] -= coeff * c
        return Polynomial(quo), Polynomial(rem)
''',
            "tests/__init__.py": "",
            "tests/test_poly.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from algebra.poly import Polynomial

def test_regular_division():
    p1 = Polynomial([1.0, 2.0, 1.0])
    p2 = Polynomial([1.0, 1.0])
    q, r = p1.quo_rem(p2)
    assert len(q.coeffs) == 2
    assert r.is_zero()

def test_zero_poly_division():
    p_zero = Polynomial([])
    p = Polynomial([1.0, 1.0])
    q, r = p_zero.quo_rem(p)
    assert q.is_zero()
    assert r.is_zero()
''',
        },
    },
    {
        "task_id": "swe_08_django_slugify_hyphens",
        "repo": "django/django-like",
        "problem_statement": (
            "In slugify(value: str) -> str, consecutive hyphens should be collapsed into a single hyphen, "
            "and leading/trailing hyphens should be stripped. Currently, slugify replaces non-alphanumeric "
            "characters with hyphens but fails to strip leading/trailing hyphens, resulting in invalid slugs "
            "like '-hello-world-'."
        ),
        "files": {
            "src/django_slug/__init__.py": "",
            "src/django_slug/slug.py": r'''from __future__ import annotations
import re
import unicodedata

def slugify(value: str) -> str:
    """Converts a string to a clean URL slug."""
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value)
''',
            "tests/__init__.py": "",
            "tests/test_slug.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from django_slug.slug import slugify

def test_simple_slug():
    assert slugify("Hello World") == "hello-world"

def test_strip_leading_trailing_hyphens():
    assert slugify("---Hello World---") == "hello-world"
''',
        },
    },
    {
        "task_id": "swe_09_sklearn_minmax_constant_feature",
        "repo": "scikit-learn/scikit-learn-like",
        "problem_statement": (
            "In MinMaxScaler.fit_transform(X: list[list[float]]) -> list[list[float]], if a feature "
            "column has constant values (i.e. max_val == min_val), dividing by (max_val - min_val) "
            "raises ZeroDivisionError. It should map constant feature columns to 0.0."
        ),
        "files": {
            "src/minmax_scaler/__init__.py": "",
            "src/minmax_scaler/scaler.py": '''from __future__ import annotations

class MinMaxScaler:
    def __init__(self, feature_range: tuple[float, float] = (0.0, 1.0)) -> None:
        self.feature_range = feature_range
        self.data_min_: list[float] = []
        self.data_max_: list[float] = []

    def fit_transform(self, X: list[list[float]]) -> list[list[float]]:
        if not X or not X[0]:
            return []
        n_features = len(X[0])
        self.data_min_ = [min(row[j] for row in X) for j in range(n_features)]
        self.data_max_ = [max(row[j] for row in X) for j in range(n_features)]

        out: list[list[float]] = []
        for row in X:
            scaled_row = []
            for j in range(n_features):
                diff = self.data_max_[j] - self.data_min_[j]
                norm = (row[j] - self.data_min_[j]) / diff
                scaled = norm * (self.feature_range[1] - self.feature_range[0]) + self.feature_range[0]
                scaled_row.append(scaled)
            out.append(scaled_row)
        return out
''',
            "tests/__init__.py": "",
            "tests/test_scaler.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from minmax_scaler.scaler import MinMaxScaler

def test_constant_feature():
    scaler = MinMaxScaler()
    X = [[5.0, 1.0], [5.0, 2.0], [5.0, 3.0]]
    res = scaler.fit_transform(X)
    assert res == [[0.0, 0.0], [0.0, 0.5], [0.0, 1.0]]
''',
        },
    },
    {
        "task_id": "swe_10_matplotlib_hex_alpha",
        "repo": "matplotlib/matplotlib-like",
        "problem_statement": (
            "In to_rgba(hex_code: str) -> tuple[float, float, float, float], 8-character hex codes "
            "like '#RRGGBBAA' should parse the 4th hex pair as the alpha channel (scaled 0.0 to 1.0). "
            "Currently, to_rgba always sets alpha to 1.0, ignoring the AA component."
        ),
        "files": {
            "src/color_parser/__init__.py": "",
            "src/color_parser/colors.py": '''from __future__ import annotations

def to_rgba(hex_code: str) -> tuple[float, float, float, float]:
    """Converts hex color string (#RGB, #RRGGBB, #RRGGBBAA) to RGBA float tuple [0.0, 1.0]."""
    s = hex_code.lstrip("#")
    if len(s) == 6:
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
        return (r, g, b, 1.0)
    elif len(s) == 8:
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
        return (r, g, b, 1.0)
    raise ValueError(f"Invalid hex color: {hex_code}")
''',
            "tests/__init__.py": "",
            "tests/test_colors.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from color_parser.colors import to_rgba

def test_hex8_with_alpha():
    r, g, b, a = to_rgba("#FF000080")
    assert (r, g, b) == (1.0, 0.0, 0.0)
    assert abs(a - 128 / 255.0) < 1e-4
''',
        },
    },
    {
        "task_id": "swe_11_pylint_unused_imports_functions",
        "repo": "pylint-dev/pylint-like",
        "problem_statement": (
            "In find_unused_imports(source: str) -> set[str], imports used inside function or class "
            "definitions should NOT be flagged as unused. Currently, the AST analyzer only checks top-level "
            "statements, incorrectly flagging symbols referenced in nested scopes."
        ),
        "files": {
            "src/linter/__init__.py": "",
            "src/linter/checker.py": '''from __future__ import annotations
import ast

def find_unused_imports(source: str) -> set[str]:
    """Finds imported module names that are never referenced in the code."""
    tree = ast.parse(source)
    imported: set[str] = set()
    used: set[str] = set()

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Name):
            used.add(node.value.id)

    return imported - used
''',
            "tests/__init__.py": "",
            "tests/test_checker.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from linter.checker import find_unused_imports

def test_import_used_inside_function():
    code = """
import math

def calculate(x):
    return math.sqrt(x)
"""
    assert find_unused_imports(code) == set()
''',
        },
    },
    {
        "task_id": "swe_12_astropy_angle_wrap",
        "repo": "astropy/astropy-like",
        "problem_statement": (
            "In wrap_angle(angle: float, lower: float = 0.0, upper: float = 360.0) -> float, "
            "the result must fall strictly in the half-open interval [lower, upper). "
            "Currently, when angle == upper, it returns upper instead of lower."
        ),
        "files": {
            "src/angles/__init__.py": "",
            "src/angles/wrapper.py": '''from __future__ import annotations

def wrap_angle(angle: float, lower: float = 0.0, upper: float = 360.0) -> float:
    """Wraps an angle into the half-open range [lower, upper)."""
    period = upper - lower
    while angle > upper:
        angle -= period
    while angle < lower:
        angle += period
    return angle
''',
            "tests/__init__.py": "",
            "tests/test_wrapper.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from angles.wrapper import wrap_angle

def test_exact_boundary():
    assert wrap_angle(360.0) == 0.0
''',
        },
    },
    {
        "task_id": "swe_13_click_choice_case_insensitive",
        "repo": "pallets/click-like",
        "problem_statement": (
            "In Choice.convert(value: str) -> str, when case_sensitive=False, matching should be "
            "case-insensitive and return the canonical choice string. Currently, convert uses strict "
            "set membership value in self.choices, raising ValueError when casing does not match."
        ),
        "files": {
            "src/click_choice/__init__.py": "",
            "src/click_choice/types.py": '''from __future__ import annotations

class Choice:
    def __init__(self, choices: list[str], case_sensitive: bool = True) -> None:
        self.choices = list(choices)
        self.case_sensitive = case_sensitive

    def convert(self, value: str) -> str:
        if value in self.choices:
            return value
        raise ValueError(f"'{value}' is not a valid choice from {self.choices}")
''',
            "tests/__init__.py": "",
            "tests/test_types.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from click_choice.types import Choice

def test_case_insensitive():
    c = Choice(["Python", "Rust"], case_sensitive=False)
    assert c.convert("python") == "Python"
''',
        },
    },
    {
        "task_id": "swe_14_urllib3_retry_string_status",
        "repo": "urllib3/urllib3-like",
        "problem_statement": (
            "In Retry.is_retry(status_code: int | str) -> bool, string status codes (e.g. '503') "
            "should be coerced to integers. Currently it performs direct set lookup on status_forcelist, "
            "returning False when status_code is passed as a string."
        ),
        "files": {
            "src/urllib_retry/__init__.py": "",
            "src/urllib_retry/util.py": '''from __future__ import annotations

class Retry:
    def __init__(self, status_forcelist: set[int] | None = None) -> None:
        self.status_forcelist = set(status_forcelist or {500, 502, 503, 504})

    def is_retry(self, status_code: int | str) -> bool:
        return status_code in self.status_forcelist
''',
            "tests/__init__.py": "",
            "tests/test_retry.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from urllib_retry.util import Retry

def test_string_status():
    r = Retry({500, 503})
    assert r.is_retry("503") is True
''',
        },
    },
    {
        "task_id": "swe_15_dataclasses_record_deepcopy",
        "repo": "cpython/dataclasses-like",
        "problem_statement": (
            "In Record.to_dict(deep: bool = True) -> dict, nested dictionary and list fields should "
            "be deep-copied when deep=True. Currently, it performs a shallow copy dict(self._fields), "
            "so mutating a list in the returned dictionary mutates the internal state of the Record."
        ),
        "files": {
            "src/record_model/__init__.py": "",
            "src/record_model/model.py": '''from __future__ import annotations
from typing import Any

class Record:
    def __init__(self, **fields: Any) -> None:
        self._fields = dict(fields)

    def to_dict(self, deep: bool = True) -> dict[str, Any]:
        return dict(self._fields)
''',
            "tests/__init__.py": "",
            "tests/test_model.py": '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from record_model.model import Record

def test_deep_copy_isolation():
    r = Record(tags=["a", "b"])
    d = r.to_dict(deep=True)
    d["tags"].append("c")
    assert r.to_dict(deep=True)["tags"] == ["a", "b"]
''',
        },
    },
]


def setup_suite() -> None:
    print(f"Creating SWE-bench Lite suite in {BENCH_ROOT}...")
    BENCH_ROOT.mkdir(parents=True, exist_ok=True)

    manifest = []
    for t in TASKS:
        task_dir = BENCH_ROOT / t["task_id"]
        task_dir.mkdir(parents=True, exist_ok=True)

        for rel_path, content in t["files"].items():
            fpath = task_dir / rel_path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")

        problem_file = task_dir / "PROBLEM.txt"
        problem_file.write_text(t["problem_statement"], encoding="utf-8")

        # Run pytest to verify baseline failure
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "-v"],
            cwd=str(task_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        print(f"Task {t['task_id']} baseline pytest exit_code={res.returncode} (expected != 0)")
        manifest.append({
            "task_id": t["task_id"],
            "repo": t["repo"],
            "problem_statement": t["problem_statement"],
            "baseline_exit_code": res.returncode,
        })

    manifest_file = BENCH_ROOT / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest written to {manifest_file}")


def reset_task(task_id: str) -> None:
    for t in TASKS:
        if t["task_id"] == task_id:
            task_dir = BENCH_ROOT / task_id
            for rel_path, content in t["files"].items():
                fpath = task_dir / rel_path
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(content, encoding="utf-8")
            return


if __name__ == "__main__":
    setup_suite()
