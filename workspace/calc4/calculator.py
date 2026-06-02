import tkinter as tk

class Calculator:
    def __init__(self, root):
        root.title("Calculator")
        root.resizable(False, False)
        root.configure(bg="#2b2b2b")

        self.expression = ""

        # Display
        self.display_var = tk.StringVar(value="0")
        display = tk.Entry(
            root,
            textvariable=self.display_var,
            font=("Helvetica", 28, "bold"),
            bg="#1e1e1e",
            fg="#ffffff",
            bd=0,
            relief="flat",
            justify="right",
            state="readonly",
            readonlybackground="#1e1e1e",
        )
        display.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=10, pady=(10, 5), ipady=18)

        # Button layout: (label, row, col, colspan, style)
        buttons = [
            ("C",  1, 0, 1, "fn"),
            ("±",  1, 1, 1, "fn"),
            ("%",  1, 2, 1, "fn"),
            ("÷",  1, 3, 1, "op"),
            ("7",  2, 0, 1, "num"),
            ("8",  2, 1, 1, "num"),
            ("9",  2, 2, 1, "num"),
            ("×",  2, 3, 1, "op"),
            ("4",  3, 0, 1, "num"),
            ("5",  3, 1, 1, "num"),
            ("6",  3, 2, 1, "num"),
            ("−",  3, 3, 1, "op"),
            ("1",  4, 0, 1, "num"),
            ("2",  4, 1, 1, "num"),
            ("3",  4, 2, 1, "num"),
            ("+",  4, 3, 1, "op"),
            ("0",  5, 0, 2, "num"),
            (".",  5, 2, 1, "num"),
            ("=",  5, 3, 1, "eq"),
        ]

        colors = {
            "fn":  {"bg": "#a5a5a5", "fg": "#000000", "active": "#c7c7c7"},
            "op":  {"bg": "#f0a500", "fg": "#ffffff", "active": "#ffbf3f"},
            "num": {"bg": "#3a3a3a", "fg": "#ffffff", "active": "#555555"},
            "eq":  {"bg": "#f0a500", "fg": "#ffffff", "active": "#ffbf3f"},
        }

        for (label, row, col, colspan, style) in buttons:
            c = colors[style]
            btn = tk.Button(
                root,
                text=label,
                font=("Helvetica", 20, "bold"),
                bg=c["bg"],
                fg=c["fg"],
                activebackground=c["active"],
                activeforeground=c["fg"],
                bd=0,
                relief="flat",
                cursor="hand2",
                command=lambda l=label: self.on_button(l),
            )
            btn.grid(
                row=row, column=col, columnspan=colspan,
                sticky="nsew", padx=4, pady=4, ipady=14,
            )

        # Make grid cells expand evenly
        for i in range(4):
            root.columnconfigure(i, weight=1, minsize=80)
        for i in range(6):
            root.rowconfigure(i, weight=1)

    # ------------------------------------------------------------------ #
    def _set(self, text):
        self.display_var.set(text)

    def on_button(self, label):
        if label == "C":
            self.expression = ""
            self._set("0")

        elif label == "±":
            try:
                val = float(self.expression) * -1
                self.expression = str(val) if val != int(val) else str(int(val))
                self._set(self.expression)
            except Exception:
                pass

        elif label == "%":
            try:
                val = float(self.expression) / 100
                self.expression = str(val) if val != int(val) else str(int(val))
                self._set(self.expression)
            except Exception:
                pass

        elif label == "=":
            try:
                # Replace display symbols with Python operators
                expr = (
                    self.expression
                    .replace("÷", "/")
                    .replace("×", "*")
                    .replace("−", "-")
                )
                result = eval(expr)  # safe here: input is button-controlled
                # Clean up float display
                if isinstance(result, float) and result == int(result):
                    result = int(result)
                self.expression = str(result)
                self._set(self.expression)
            except ZeroDivisionError:
                self._set("Error")
                self.expression = ""
            except Exception:
                self._set("Error")
                self.expression = ""

        else:
            # Digit / operator / decimal
            if self.expression == "" and label in "÷×−+":
                return  # ignore leading operator
            self.expression += label
            self._set(self.expression)


def main():
    root = tk.Tk()
    Calculator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
