"""Calculator tool with safe AST evaluation — no eval(), no arbitrary code execution."""

import ast
import math
import operator
from typing import Any
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult


class CalculatorInput(BaseModel):
    """Input parameters for the calculator tool."""

    expression: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="The mathematical expression to evaluate, e.g. '(15 * 40) / 2' or 'sqrt(256) + 14'",
    )


class SafeCalculator:
    """Evaluates mathematical expressions safely using Python's AST module."""

    # Supported binary operators
    _BINARY_OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    # Supported unary operators
    _UNARY_OPS = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    # Supported mathematical functions
    _FUNCTIONS = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sqrt": math.sqrt,
        "pow": pow,
        "ceil": math.ceil,
        "floor": math.floor,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
    }

    # Mathematical constants
    _CONSTANTS = {
        "pi": math.pi,
        "e": math.e,
    }

    def evaluate(self, expression: str) -> float | int:
        """Parse and safely evaluate the expression."""
        cleaned = expression.strip()
        if not cleaned:
            raise ValueError("Expression cannot be empty")

        try:
            tree = ast.parse(cleaned, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid mathematical syntax: {e.msg}") from e

        return self._eval_node(tree.body)

    def _eval_node(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

        elif isinstance(node, ast.Name):
            name_lower = node.id.lower()
            if name_lower in self._CONSTANTS:
                return self._CONSTANTS[name_lower]
            raise ValueError(f"Unknown variable or constant: '{node.id}'")

        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            op_type = type(node.op)

            if op_type not in self._BINARY_OPS:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")

            if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
                raise ZeroDivisionError("Division or modulo by zero is not allowed")

            # Check for excessive power operations to avoid denial of service
            if op_type == ast.Pow:
                if abs(right) > 1000 or (abs(left) > 10 and right > 100):
                    raise OverflowError("Exponentiation result exceeds safe limits")

            result = self._BINARY_OPS[op_type](left, right)
            if isinstance(result, complex):
                raise ValueError("Complex numbers are not supported")
            if math.isnan(result) or math.isinf(result):
                raise OverflowError("Calculation resulted in NaN or Infinity")
            return result

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            op_type = type(node.op)
            if op_type not in self._UNARY_OPS:
                raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
            return self._UNARY_OPS[op_type](operand)

        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only named function calls are permitted")
            func_name = node.func.id.lower()
            if func_name not in self._FUNCTIONS:
                raise ValueError(f"Function '{node.func.id}' is not permitted")

            args = [self._eval_node(arg) for arg in node.args]
            try:
                result = self._FUNCTIONS[func_name](*args)
            except Exception as e:
                raise ValueError(f"Error calculating {func_name}(): {str(e)}") from e

            if isinstance(result, complex):
                raise ValueError("Complex numbers are not supported")
            if isinstance(result, float) and (math.isnan(result) or math.isinf(result)):
                raise OverflowError("Function result is NaN or Infinity")
            return result

        else:
            raise ValueError(
                f"Unsupported syntax: '{type(node).__name__}'. Only arithmetic expressions are allowed."
            )


class CalculatorTool(BaseTool):
    """Tool for performing deterministic arithmetic calculations."""

    name = "calculator"
    description = (
        "Perform exact mathematical calculations (addition, subtraction, multiplication, "
        "division, powers, sqrt, abs, round, min, max, etc.). Always use this tool for arithmetic "
        "instead of guessing."
    )
    args_schema = CalculatorInput

    def __init__(self):
        self._calculator = SafeCalculator()

    async def execute(self, expression: str, **kwargs) -> ToolResult:
        """Execute the calculation safely."""
        try:
            result = self._calculator.evaluate(expression)
            # Format nicely: integer if whole number
            formatted = int(result) if isinstance(result, float) and result.is_integer() else result
            summary = f"{expression} = {formatted}"

            return ToolResult(
                success=True,
                tool_name=self.name,
                summary=summary,
                output={
                    "expression": expression,
                    "result": formatted,
                },
                metadata={"expression": expression},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                tool_name=self.name,
                summary=f"Calculation error: {str(e)}",
                error=str(e),
                metadata={"expression": expression},
            )
