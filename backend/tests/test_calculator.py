"""Unit tests for the SafeCalculator and CalculatorTool."""

import pytest
from app.tools.calculator import SafeCalculator, CalculatorTool


def test_basic_arithmetic():
    calc = SafeCalculator()
    assert calc.evaluate("2 + 2") == 4
    assert calc.evaluate("10 - 4") == 6
    assert calc.evaluate("6 * 7") == 42
    assert calc.evaluate("20 / 4") == 5.0
    assert calc.evaluate("17 // 3") == 5
    assert calc.evaluate("17 % 5") == 2
    assert calc.evaluate("2 ** 8") == 256


def test_operator_precedence_and_parentheses():
    calc = SafeCalculator()
    assert calc.evaluate("2 + 3 * 4") == 14
    assert calc.evaluate("(2 + 3) * 4") == 20
    assert calc.evaluate("((100 - 20) / 4) + 5") == 25.0


def test_supported_functions():
    calc = SafeCalculator()
    assert calc.evaluate("sqrt(144)") == 12.0
    assert calc.evaluate("abs(-42)") == 42
    assert calc.evaluate("round(3.14159, 2)") == 3.14
    assert calc.evaluate("min(10, 5, 20)") == 5
    assert calc.evaluate("max(10, 5, 20)") == 20
    assert calc.evaluate("ceil(4.2)") == 5
    assert calc.evaluate("floor(4.8)") == 4


def test_division_by_zero():
    calc = SafeCalculator()
    with pytest.raises(ZeroDivisionError):
        calc.evaluate("10 / 0")

    with pytest.raises(ZeroDivisionError):
        calc.evaluate("10 // 0")

    with pytest.raises(ZeroDivisionError):
        calc.evaluate("10 % 0")


def test_arbitrary_code_execution_blocked():
    calc = SafeCalculator()

    # Block imports
    with pytest.raises(ValueError):
        calc.evaluate("__import__('os').system('ls')")

    # Block exec/eval
    with pytest.raises(ValueError):
        calc.evaluate("eval('2 + 2')")

    # Block arbitrary variables
    with pytest.raises(ValueError):
        calc.evaluate("foo + 1")

    # Block string/list literals
    with pytest.raises(ValueError):
        calc.evaluate("'hello' + 'world'")

    # Block attribute lookups
    with pytest.raises(ValueError):
        calc.evaluate("(1).__class__")


def test_syntax_errors():
    calc = SafeCalculator()
    with pytest.raises(ValueError, match="Invalid mathematical syntax"):
        calc.evaluate("2 + + + * 4")

    with pytest.raises(ValueError, match="Expression cannot be empty"):
        calc.evaluate("   ")


@pytest.mark.asyncio
async def test_calculator_tool_success():
    tool = CalculatorTool()
    result = await tool.execute(expression="(1500 * 12) / 2")

    assert result.success is True
    assert result.tool_name == "calculator"
    assert result.output["result"] == 9000
    assert "(1500 * 12) / 2 = 9000" in result.summary


@pytest.mark.asyncio
async def test_calculator_tool_failure():
    tool = CalculatorTool()
    result = await tool.execute(expression="5 / 0")

    assert result.success is False
    assert result.error is not None
    assert "zero" in result.error.lower()
