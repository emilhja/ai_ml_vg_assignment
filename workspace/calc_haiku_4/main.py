import tkinter as tk
from calculator_ui import CalculatorUI


def main():
    root = tk.Tk()
    root.title("Calculator")
    CalculatorUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
