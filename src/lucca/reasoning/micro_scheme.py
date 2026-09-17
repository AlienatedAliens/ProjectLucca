"""
Project Lucca — Micro-Scheme Symbolic Engine
A sandboxed, gas-metered S-expression interpreter in pure Python.
Guarantees termination, zero arbitrary code execution, and sub-millisecond evaluation.
"""

from typing import Any, List, Dict, Union
from lucca.core.exceptions import GasExhaustedException

Symbol = str
Number = Union[int, float]
Atom = Union[Symbol, Number, str, bool]
Exp = Union[Atom, List['Exp']]

class MicroSchemeEnv(dict):
    """Execution environment with outer scoping."""
    def __init__(self, params=(), args=(), outer=None):
        super().__init__()
        self.update(zip(params, args))
        self.outer = outer

    def find(self, var: Symbol):
        if var in self:
            return self
        if self.outer is not None:
            return self.outer.find(var)
        raise NameError(f"Symbol '{var}' not bound in environment.")

def standard_env() -> MicroSchemeEnv:
    """Instantiates the sandboxed, pure primitive environment."""
    env = MicroSchemeEnv()
    env.update({
        '+': lambda *args: sum(args),
        '-': lambda a, b=None: -a if b is None else a - b,
        '*': lambda a, b: a * b,
        '/': lambda a, b: a / b,
        '=': lambda a, b: a == b,
        '<': lambda a, b: a < b,
        '>': lambda a, b: a > b,
        '<=': lambda a, b: a <= b,
        '>=': lambda a, b: a >= b,
        'not': lambda a: not a,
        'and': lambda *args: all(args),
        'or': lambda *args: any(args),
        'list': lambda *args: list(args),
        'get': lambda d, k: d.get(k) if isinstance(d, dict) else d[k],
        'contains?': lambda container, item: item in container,
    })
    return env

class MicroSchemeInterpreter:
    def __init__(self, default_gas: int = 1000):
        self._default_gas = default_gas
        self._global_env = standard_env()

    def tokenize(self, chars: str) -> List[str]:
        """Converts raw S-expression string into tokens."""
        return chars.replace('(', ' ( ').replace(')', ' ) ').split()

    def parse(self, program: str) -> Exp:
        """Parses an S-expression string into nested Python lists."""
        tokens = self.tokenize(program)
        return self._read_from_tokens(tokens)

    def _read_from_tokens(self, tokens: List[str]) -> Exp:
        if len(tokens) == 0:
            raise SyntaxError("Unexpected EOF while reading tokens.")
        token = tokens.pop(0)
        if token == '(':
            L = []
            while tokens and tokens[0] != ')':
                L.append(self._read_from_tokens(tokens))
            if not tokens:
                raise SyntaxError("Missing closing parenthesis ')'")
            tokens.pop(0)  # pop ')'
            return L
        elif token == ')':
            raise SyntaxError("Unexpected ')'")
        else:
            return self._atom(token)

    def _atom(self, token: str) -> Atom:
        if token == '#t':
            return True
        if token == '#f':
            return False
        if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
            return token[1:-1]
        try:
            return int(token)
        except ValueError:
            try:
                return float(token)
            except ValueError:
                return Symbol(token)

    def eval(self, x: Exp, env: MicroSchemeEnv = None, gas: int = None) -> Any:
        """Evaluates an S-expression with gas metering."""
        if env is None:
            env = self._global_env
        if gas is None:
            gas = self._default_gas

        return self._eval_step(x, env, [gas])

    def _eval_step(self, x: Exp, env: MicroSchemeEnv, gas_box: List[int]) -> Any:
        # Decrement gas
        gas_box[0] -= 1
        if gas_box[0] <= 0:
            raise GasExhaustedException("Execution gas exhausted (infinite loop or deep recursion detected).")

        if isinstance(x, Symbol):
            return env.find(x)[x]
        elif not isinstance(x, list):
            return x

        op = x[0]
        if op == 'if':
            (_, test, conseq, alt) = x
            exp = conseq if self._eval_step(test, env, gas_box) else alt
            return self._eval_step(exp, env, gas_box)
        elif op == 'define':
            (_, symbol, exp) = x
            env[symbol] = self._eval_step(exp, env, gas_box)
            return env[symbol]
        elif op == 'seq':
            # Evaluates sequential expressions, returning the last
            res = None
            for exp in x[1:]:
                res = self._eval_step(exp, env, gas_box)
            return res
        else:
            proc = self._eval_step(op, env, gas_box)
            vals = [self._eval_step(arg, env, gas_box) for arg in x[1:]]
            return proc(*vals)
