
import sys
from unittest.mock import MagicMock, patch

# --- Stub out tkinter entirely before any import touches it ---
tk_mock = MagicMock()
sys.modules['tkinter'] = tk_mock
sys.modules['tkinter.messagebox'] = tk_mock.messagebox

# We need StringVar to behave like a real StringVar (get/set)
class FakeStringVar:
    def __init__(self, *a, **kw):
        self._val = ""
    def get(self):
        return self._val
    def set(self, v):
        self._val = v

tk_mock.StringVar = FakeStringVar
tk_mock.Frame = MagicMock
tk_mock.Entry = MagicMock
tk_mock.Button = MagicMock

import pytest

sys.path.insert(0, 'calc2')
from workspace.archive.calc2.calculator import Calculator


@pytest.fixture
def calculator():
    root = MagicMock()
    calc = Calculator(root)
    calc.input_text = FakeStringVar()
    tk_mock.messagebox.showerror.reset_mock()
    yield calc

def test_button_click(calculator):
    calculator.button_click('5')
    assert calculator.expression == '5'
    assert calculator.input_text.get() == '5'

def test_clear_button(calculator):
    calculator.expression = '123'
    calculator.input_text.set('123')
    calculator.clear_button()
    assert calculator.expression == ''
    assert calculator.input_text.get() == ''

def test_backspace_button(calculator):
    calculator.expression = '123'
    calculator.input_text.set('123')
    calculator.backspace_button()
    assert calculator.expression == '12'
    assert calculator.input_text.get() == '12'

    calculator.backspace_button()
    calculator.backspace_button()
    calculator.backspace_button()
    assert calculator.expression == ''
    assert calculator.input_text.get() == ''

def test_equal_button_valid_expression(calculator):
    calculator.expression = '2+3'
    calculator.equal_button()
    assert calculator.expression == '5'
    assert calculator.input_text.get() == '5'

def test_equal_button_division_by_zero(calculator):
    calculator.expression = '1/0'
    calculator.equal_button()
    assert calculator.expression == ''
    assert calculator.input_text.get() == ''
    tk_mock.messagebox.showerror.assert_called_once_with(
        "Error", "Cannot divide by zero"
    )

def test_equal_button_invalid_syntax(calculator):
    calculator.expression = '2+'
    calculator.equal_button()
    assert calculator.expression == ''
    assert calculator.input_text.get() == ''
    tk_mock.messagebox.showerror.assert_called_once_with(
        "Error", "Invalid Expression"
    )

def test_key_press_digit(calculator):
    event = MagicMock()
    event.char = '7'
    calculator.key_press(event)
    assert calculator.expression == '7'
    assert calculator.input_text.get() == '7'

def test_key_press_c_clear(calculator):
    calculator.expression = '123'
    calculator.input_text.set('123')
    event = MagicMock()
    event.char = 'c'
    calculator.key_press(event)
    assert calculator.expression == ''
    assert calculator.input_text.get() == ''

def test_key_press_C_clear(calculator):
    calculator.expression = '123'
    calculator.input_text.set('123')
    event = MagicMock()
    event.char = 'C'
    calculator.key_press(event)
    assert calculator.expression == ''
    assert calculator.input_text.get() == ''
