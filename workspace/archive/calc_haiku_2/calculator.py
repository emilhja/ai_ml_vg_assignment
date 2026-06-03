import tkinter as tk


class Calculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Calculator")
        self.resizable(False, False)
        self.geometry("320x480")
        self.configure(bg="#2b2b2b")

        self._expression = ""
        self._build_ui()
        self._bind_keys()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        # Display
        self._display_var = tk.StringVar(value="0")
        display = tk.Entry(
            self,
            textvariable=self._display_var,
            font=("Helvetica", 28, "bold"),
            bd=0,
            bg="#1c1c1c",
            fg="white",
            insertbackground="white",
            justify="right",
            state="readonly",
            readonlybackground="#1c1c1c",
        )
        display.pack(fill="x", padx=10, pady=(16, 8), ipady=14)

        # Button grid frame
        grid_frame = tk.Frame(self, bg="#2b2b2b")
        grid_frame.pack(fill="both", expand=True, padx=6, pady=6)

        # Button layout: (label, row, col, colspan, style)
        buttons = [
            ("C",  0, 0, 1, "clear"),
            ("⌫",  0, 1, 1, "op"),
            ("%",  0, 2, 1, "op"),
            ("/",  0, 3, 1, "op"),
            ("7",  1, 0, 1, "digit"),
            ("8",  1, 1, 1, "digit"),
            ("9",  1, 2, 1, "digit"),
            ("*",  1, 3, 1, "op"),
            ("4",  2, 0, 1, "digit"),
            ("5",  2, 1, 1, "digit"),
            ("6",  2, 2, 1, "digit"),
            ("-",  2, 3, 1, "op"),
            ("1",  3, 0, 1, "digit"),
            ("2",  3, 1, 1, "digit"),
            ("3",  3, 2, 1, "digit"),
            ("+",  3, 3, 1, "op"),
            ("+/-",4, 0, 1, "digit"),
            ("0",  4, 1, 1, "digit"),
            (".",  4, 2, 1, "digit"),
            ("=",  4, 3, 1, "equals"),
        ]

        styles = {
            "digit":  {"bg": "#3c3c3c", "fg": "white",   "activebackground": "#505050"},
            "op":     {"bg": "#ff9500", "fg": "white",   "activebackground": "#ffaa33"},
            "clear":  {"bg": "#f44336", "fg": "white",   "activebackground": "#e53935"},
            "equals": {"bg": "#4caf50", "fg": "white",   "activebackground": "#43a047"},
        }

        for col in range(4):
            grid_frame.columnconfigure(col, weight=1)
        for row in range(5):
            grid_frame.rowconfigure(row, weight=1)

        for (label, row, col, colspan, style) in buttons:
            s = styles[style]
            btn = tk.Button(
                grid_frame,
                text=label,
                font=("Helvetica", 18, "bold"),
                bd=0,
                relief="flat",
                cursor="hand2",
                command=lambda lbl=label: self._on_button(lbl),
                **s,
            )
            btn.grid(
                row=row, column=col, columnspan=colspan,
                sticky="nsew", padx=3, pady=3,
            )

    # ------------------------------------------------------------------
    # Keyboard bindings
    # ------------------------------------------------------------------
    def _bind_keys(self):
        for key in "0123456789.+-*/%":
            self.bind(key, lambda e, k=key: self._on_button(k))
        self.bind("<Return>",    lambda e: self._on_button("="))
        self.bind("<KP_Enter>",  lambda e: self._on_button("="))
        self.bind("<BackSpace>", lambda e: self._on_button("⌫"))
        self.bind("<Escape>",    lambda e: self._on_button("C"))

    # ------------------------------------------------------------------
    # Button logic
    # ------------------------------------------------------------------
    def _on_button(self, label: str):
        if label == "C":
            self._expression = ""
            self._display_var.set("0")
        elif label == "⌫":
            self._expression = self._expression[:-1]
            self._display_var.set(self._expression if self._expression else "0")
        elif label == "=":
            self._evaluate()
        elif label == "+/-":
            self._toggle_sign()
        else:
            self._expression += label
            self._display_var.set(self._expression)

    def _evaluate(self):
        try:
            result = eval(self._expression)  # noqa: S307
            # Format: drop unnecessary decimals
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            self._expression = str(result)
            self._display_var.set(self._expression)
        except ZeroDivisionError:
            self._display_var.set("Error: Div/0")
            self._expression = ""
        except Exception:
            self._display_var.set("Error")
            self._expression = ""

    def _toggle_sign(self):
        try:
            val = float(self._expression)
            val = -val
            self._expression = str(int(val) if val == int(val) else val)
            self._display_var.set(self._expression)
        except Exception:
            pass
