import tkinter as tk
from .calculator_engine import CalculatorEngine
from .calculator_ui import CalculatorUI


def main():
    root = tk.Tk()
    engine = CalculatorEngine()
    ui = CalculatorUI(root, engine)
    ui.run()


if __name__ == "__main__":
    main()
