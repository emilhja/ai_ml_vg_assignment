
import tkinter as tk

class Calculator:
    def __init__(self, master):
        self.master = master
        master.title("Gemini Calculator")
        master.geometry("300x400")
        master.resizable(False, False)

        self.expression = ""
        self.input_text = tk.StringVar()

        input_frame = tk.Frame(master, width=300, height=50, bd=0, highlightbackground="black", highlightcolor="black", highlightthickness=1)
        input_frame.pack(side=tk.TOP)

        input_field = tk.Entry(input_frame, font=('arial', 18, 'bold'), textvariable=self.input_text, width=20, bg="#eee", bd=0, justify=tk.RIGHT)
        input_field.grid(row=0, column=0)
        input_field.pack(ipady=10)

        btns_frame = tk.Frame(master, width=300, height=350, bg="grey")
        btns_frame.pack()

        # First row: Clear and Backspace
        clear = tk.Button(btns_frame, text="C", fg="black", width=8, height=2, bd=0, bg="#eee", cursor="hand cursor", command=self.clear_all)
        clear.grid(row=0, column=0, columnspan=2, padx=1, pady=1)
        backspace = tk.Button(btns_frame, text="⌫", fg="black", width=8, height=2, bd=0, bg="#eee", cursor="hand cursor", command=self.backspace)
        backspace.grid(row=0, column=2, columnspan=2, padx=1, pady=1)

        # Second row: 7, 8, 9, /
        seven = tk.Button(btns_frame, text="7", fg="black", width=4, height=2, bd=0, bg="#fff", cursor="hand cursor", command=lambda: self.btn_click(7))
        seven.grid(row=1, column=0, padx=1, pady=1)
        eight = tk.Button(btns_frame, text="8", fg="black", width=4, height=2, bd=0, bg="#fff", cursor="hand cursor", command=lambda: self.btn_click(8))
        eight.grid(row=1, column=1, padx=1, pady=1)
        nine = tk.Button(btns_frame, text="9", fg="black", width=4, height=2, bd=0, bg="#fff", cursor="hand cursor", command=lambda: self.btn_click(9))
        nine.grid(row=1, column=2, padx=1, pady=1)
        divide = tk.Button(btns_frame, text="÷", fg="black", width=4, height=2, bd=0, bg="#eee", cursor="hand cursor", command=lambda: self.btn_click("/"))
        divide.grid(row=1, column=3, padx=1, pady=1)

        # Third row: 4, 5, 6, *
        four = tk.Button(btns_frame, text="4", fg="black", width=4, height=2, bd=0, bg="#fff", cursor="hand cursor", command=lambda: self.btn_click(4))
        four.grid(row=2, column=0, padx=1, pady=1)
        five = tk.Button(btns_frame, text="5", fg="black", width=4, height=2, bd=0, bg="#fff", cursor="hand cursor", command=lambda: self.btn_click(5))
        five.grid(row=2, column=1, padx=1, pady=1)
        six = tk.Button(btns_frame, text="6", fg="black", width=4, height=2, bd=0, bg="#fff", cursor="hand cursor", command=lambda: self.btn_click(6))
        six.grid(row=2, column=2, padx=1, pady=1)
        multiply = tk.Button(btns_frame, text="×", fg="black", width=4, height=2, bd=0, bg="#eee", cursor="hand cursor", command=lambda: self.btn_click("*"))
        multiply.grid(row=2, column=3, padx=1, pady=1)

        # Fourth row: 1, 2, 3, -
        one = tk.Button(btns_frame, text="1", fg="black", width=4, height=2, bd=0, bg="#fff", cursor="hand cursor", command=lambda: self.btn_click(1))
        one.grid(row=3, column=0, padx=1, pady=1)
        two = tk.Button(btns_frame, text="2", fg="black", width=4, height=2, bd=0, bg="#fff", cursor="hand cursor", command=lambda: self.btn_click(2))
        two.grid(row=3, column=1, padx=1, pady=1)
        three = tk.Button(btns_frame, text="3", fg="black", width=4, height=2, bd=0, bg="#fff", cursor="hand cursor", command=lambda: self.btn_click(3))
        three.grid(row=3, column=2, padx=1, pady=1)
        minus = tk.Button(btns_frame, text="-", fg="black", width=4, height=2, bd=0, bg="#eee", cursor="hand cursor", command=lambda: self.btn_click("-"))
        minus.grid(row=3, column=3, padx=1, pady=1)

        # Fifth row: 0, ., =, +
        zero = tk.Button(btns_frame, text="0", fg="black", width=4, height=2, bd=0, bg="#fff", cursor="hand cursor", command=lambda: self.btn_click(0))
        zero.grid(row=4, column=0, padx=1, pady=1)
        point = tk.Button(btns_frame, text=".", fg="black", width=4, height=2, bd=0, bg="#eee", cursor="hand cursor", command=lambda: self.btn_click("."))
        point.grid(row=4, column=1, padx=1, pady=1)
        equals = tk.Button(btns_frame, text="=", fg="black", width=4, height=2, bd=0, bg="#eee", cursor="hand cursor", command=self.evaluate, highlightbackground="blue")
        equals.grid(row=4, column=2, padx=1, pady=1)
        plus = tk.Button(btns_frame, text="+", fg="black", width=4, height=2, bd=0, bg="#eee", cursor="hand cursor", command=lambda: self.btn_click("+"))
        plus.grid(row=4, column=3, padx=1, pady=1)

    def btn_click(self, item):
        self.expression = self.expression + str(item)
        self.input_text.set(self.expression)

    def clear_all(self):
        self.expression = ""
        self.input_text.set("")

    def backspace(self):
        self.expression = self.expression[:-1]
        self.input_text.set(self.expression)

    def evaluate(self):
        try:
            # Replace '÷' with '/' and '×' with '*' for evaluation
            expression_to_eval = self.expression.replace('÷', '/').replace('×', '*')
            result = str(eval(expression_to_eval))
            self.input_text.set(result)
            self.expression = result
        except ZeroDivisionError:
            self.input_text.set("Error")
            self.expression = ""
        except Exception:
            self.input_text.set("Error")
            self.expression = ""

if __name__ == "__main__":
    root = tk.Tk()
    my_gui = Calculator(root)
    root.mainloop()
