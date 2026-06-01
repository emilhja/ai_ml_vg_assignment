import tkinter as tk

class Calculator:
    def __init__(self, master):
        self.master = master
        master.title("Calculator")

        self.display = tk.Entry(master, width=25, borderwidth=5)
        self.display.grid(row=0, column=0, columnspan=4, padx=10, pady=10)

        # Define buttons
        buttons = [
            '7', '8', '9', '/',
            '4', '5', '6', '*',
            '1', '2', '3', '-',
            '0', '.', '=', '+',
        ]

        # Add buttons to the grid
        row_val = 1
        col_val = 0
        for button in buttons:
            tk.Button(master, text=button, padx=20, pady=20,
                      command=lambda b=button: self.button_click(b)).grid(row=row_val, column=col_val)
            col_val += 1
            if col_val > 3:
                col_val = 0
                row_val += 1

    def button_click(self, button):
        current = self.display.get()
        if button == '=':
            try:
                result = str(eval(current))
                self.display.delete(0, tk.END)
                self.display.insert(0, result)
            except Exception as e:
                self.display.delete(0, tk.END)
                self.display.insert(0, "Error")
        else:
            self.display.insert(tk.END, button)
        # Handle button clicks here
        pass

root = tk.Tk()
calculator = Calculator(root)
root.mainloop()
