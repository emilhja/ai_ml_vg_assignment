import tkinter as tk
from . import CalculatorEngine, CalculatorApp


def main():
    root = tk.Tk()
    engine = CalculatorEngine()
    app = CalculatorApp(root, engine)
    app.run()


if __name__ == "__main__":
    main()
