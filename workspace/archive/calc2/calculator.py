import tkinter as tk
from tkinter import messagebox

class Calculator:
    def __init__(self, master):
        self.master = master
        master.title("Calculator")
        master.geometry("300x400")
        master.resizable(0, 0)
        master.configure(bg="#2E2E2E")

        self.expression = ""
        self.input_text = tk.StringVar()

        self.create_widgets()
        self.bind_keys()

    def create_widgets(self):
        # Display screen
        input_frame = tk.Frame(self.master, bd=0, relief=tk.RIDGE, bg="#2E2E2E")
        input_frame.pack(side=tk.TOP)

        input_field = tk.Entry(input_frame, font=('arial', 18, 'bold'),
                               textvariable=self.input_text, width=20,
                               bg="#505050", fg="white", bd=0, justify=tk.RIGHT)
        input_field.grid(row=0, column=0, ipady=10)

        # Buttons frame
        btns_frame = tk.Frame(self.master, bg="#2E2E2E")
        btns_frame.pack()

        # Row 1: C, Backspace, /, *
        self.create_button(btns_frame, "C", 1, 0, self.clear_button, "#D4D4D2")
        self.create_button(btns_frame, "⌫", 1, 1, self.backspace_button, "#D4D4D2")
        self.create_button(btns_frame, "/", 1, 2, self.button_click, "#FF9500")
        self.create_button(btns_frame, "*", 1, 3, self.button_click, "#FF9500")

        # Row 2: 7, 8, 9, -
        self.create_button(btns_frame, "7", 2, 0, self.button_click, "#505050")
        self.create_button(btns_frame, "8", 2, 1, self.button_click, "#505050")
        self.create_button(btns_frame, "9", 2, 2, self.button_click, "#505050")
        self.create_button(btns_frame, "-", 2, 3, self.button_click, "#FF9500")

        # Row 3: 4, 5, 6, +
        self.create_button(btns_frame, "4", 3, 0, self.button_click, "#505050")
        self.create_button(btns_frame, "5", 3, 1, self.button_click, "#505050")
        self.create_button(btns_frame, "6", 3, 2, self.button_click, "#505050")
        self.create_button(btns_frame, "+", 3, 3, self.button_click, "#FF9500")

        # Row 4: 1, 2, 3, =
        self.create_button(btns_frame, "1", 4, 0, self.button_click, "#505050")
        self.create_button(btns_frame, "2", 4, 1, self.button_click, "#505050")
        self.create_button(btns_frame, "3", 4, 2, self.button_click, "#505050")
        self.create_button(btns_frame, "=", 4, 3, self.equal_button, "#FF9500", rowspan=2)

        # Row 5: 0, ., (
        self.create_button(btns_frame, "0", 5, 0, self.button_click, "#505050", columnspan=2)
        self.create_button(btns_frame, ".", 5, 2, self.button_click, "#505050")

    def create_button(self, parent, text, row, column, command, bg_color, columnspan=1, rowspan=1):
        button = tk.Button(parent, text=text, fg="white", width=7, height=3, bd=0,
                           bg=bg_color, cursor="hand2", command=lambda: command(text))
        button.grid(row=row, column=column, columnspan=columnspan, rowspan=rowspan, padx=1, pady=1)

    def bind_keys(self):
        self.master.bind("<Key>", self.key_press)
        self.master.bind("<BackSpace>", lambda event: self.backspace_button())
        self.master.bind("<Return>", lambda event: self.equal_button())
        self.master.bind("<KP_Enter>", lambda event: self.equal_button())

    def button_click(self, item):
        self.expression += str(item)
        self.input_text.set(self.expression)

    def clear_button(self, event=None):
        self.expression = ""
        self.input_text.set("")

    def backspace_button(self, event=None):
        self.expression = self.expression[:-1]
        self.input_text.set(self.expression)

    def equal_button(self, event=None):
        try:
            result = str(eval(self.expression))
            self.input_text.set(result)
            self.expression = result
        except ZeroDivisionError:
            messagebox.showerror("Error", "Cannot divide by zero")
            self.expression = ""
            self.input_text.set("")
        except SyntaxError:
            messagebox.showerror("Error", "Invalid Expression")
            self.expression = ""
            self.input_text.set("")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")
            self.expression = ""
            self.input_text.set("")

    def key_press(self, event):
        key = event.char
        if key.isdigit() or key in "+-*/.()":
            self.button_click(key)
        elif key == 'c' or key == 'C':
            self.clear_button()

if __name__ == "__main__":
    root = tk.Tk()
    calculator = Calculator(root)
    root.mainloop()