import tkinter as tk
from . import CalculatorEngine, CalculatorUI


def main():
    root = tk.Tk()
    engine = CalculatorEngine()
    ui = CalculatorUI(root, engine)
    ui.run()


if __name__ == "__main__":
    main()
