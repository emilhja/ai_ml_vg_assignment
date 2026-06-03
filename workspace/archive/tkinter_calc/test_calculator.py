import tkinter as tk

from workspace.archive.tkinter_calc.calculator import Calculator


def test_calculator_initialization():
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    calculator = Calculator(root)
    assert isinstance(calculator.master, tk.Tk)
    assert calculator.master == root
    root.destroy()

def test_button_click_updates_expression():
    root = tk.Tk()
    root.withdraw()
    calculator = Calculator(root)

    # Simulate button clicks
    calculator.button_click('1')
    calculator.button_click('+')
    calculator.button_click('2')

    assert calculator.expression.get() == '1+2'
    root.destroy()

def test_clear_button():
    root = tk.Tk()
    root.withdraw()
    calculator = Calculator(root)

    calculator.button_click('1')
    calculator.clear_expression()
    assert calculator.expression.get() == ''
    root.destroy()

def test_evaluate_expression():
    root = tk.Tk()
    root.withdraw()
    calculator = Calculator(root)

    calculator.expression.set('1+2*3')
    calculator.evaluate_expression()
    assert calculator.expression.get() == '7'

    calculator.expression.set('10/2')
    calculator.evaluate_expression()
    assert calculator.expression.get() == '5.0'

    calculator.expression.set('7-3')
    calculator.evaluate_expression()
    assert calculator.expression.get() == '4'
    root.destroy()

def test_evaluate_zero_division():
    root = tk.Tk()
    root.withdraw()
    calculator = Calculator(root)

    calculator.expression.set('1/0')
    calculator.evaluate_expression()
    assert calculator.expression.get() == 'Error'
    root.destroy()

def test_evaluate_syntax_error():
    root = tk.Tk()
    root.withdraw()
    calculator = Calculator(root)

    calculator.expression.set('1+')
    calculator.evaluate_expression()
    assert calculator.expression.get() == 'Error'
    root.destroy()
