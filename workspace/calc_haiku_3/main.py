import tkinter as tk
from calc_haiku_3.calculator_ui import CalculatorApp

if __name__ == '__main__':
    root = tk.Tk()
    root.title('Calculator')
    root.resizable(False, False)
    app = CalculatorApp(master=root)
    app.pack(fill='both', expand=True)
    root.mainloop()
