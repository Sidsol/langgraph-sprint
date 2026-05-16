from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from typing import Final

_ALLOWED_BINOPS: Final[dict[type[ast.operator], Callable[[float, float], float]]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}

_ALLOWED_UNARYOPS: Final[dict[type[ast.unaryop], Callable[[float], float]]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def safe_calc(expression: str) -> float:
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("unsafe expression") from exc

    try:
        return float(_eval_node(parsed.body))
    except ZeroDivisionError as exc:
        raise ValueError("invalid arithmetic operation") from exc


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise ValueError("unsafe expression")
        return float(node.value)

    if isinstance(node, ast.BinOp):
        operator_type = type(node.op)
        if operator_type not in _ALLOWED_BINOPS:
            raise ValueError("unsafe expression")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return float(_ALLOWED_BINOPS[operator_type](left, right))

    if isinstance(node, ast.UnaryOp):
        operator_type = type(node.op)
        if operator_type not in _ALLOWED_UNARYOPS:
            raise ValueError("unsafe expression")
        operand = _eval_node(node.operand)
        return float(_ALLOWED_UNARYOPS[operator_type](operand))

    raise ValueError("unsafe expression")


__all__ = ["safe_calc"]
