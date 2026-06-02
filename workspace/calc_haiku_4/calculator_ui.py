import tkinter as tk


class CalculatorUI:
    def __init__(self, root: tk.Tk, engine):
        """
        root   — the Tk root window
        engine — a CalculatorEngine instance (duck-typed, injected by main.py)
        """
        self.root = root
        self.engine = engine
        self._build_ui()

    def _build_ui(self):
        self.root.title('Calculator')
        self.root.resizable(False, False)
        self.root.configure(bg='#1c1c1e')

        # Display label
        self.display_var = tk.StringVar(value='0')
        display = tk.Label(
            self.root, textvariable=self.display_var,
            font=('Helvetica', 36, 'bold'), bg='#1c1c1e', fg='white',
            anchor='e', padx=16, pady=12, width=12
        )
        display.grid(row=0, column=0, columnspan=4, sticky='ew')

        # Button layout: (label, row, col, style) or (label, row, col, style, colspan)
        buttons = [
            ('AC', 1, 0, 'fn'), ('+/-', 1, 1, 'fn'), ('%', 1, 2, 'fn'), ('÷', 1, 3, 'op'),
            ('7',  2, 0, 'num'), ('8',  2, 1, 'num'), ('9', 2, 2, 'num'), ('×', 2, 3, 'op'),
            ('4',  3, 0, 'num'), ('5',  3, 1, 'num'), ('6', 3, 2, 'num'), ('-', 3, 3, 'op'),
            ('1',  4, 0, 'num'), ('2',  4, 1, 'num'), ('3', 4, 2, 'num'), ('+', 4, 3, 'op'),
            ('0',  5, 0, 'num', 2),                   ('.', 5, 2, 'num'), ('=', 5, 3, 'op'),
        ]

        colours = {
            'fn':  {'bg': '#636366', 'fg': 'white', 'abg': '#8e8e93'},
            'op':  {'bg': '#ff9f0a', 'fg': 'white', 'abg': '#ffb340'},
            'num': {'bg': '#3a3a3c', 'fg': 'white', 'abg': '#636366'},
        }

        for item in buttons:
            if len(item) == 5:
                label, row, col, style, colspan = item
            else:
                label, row, col, style = item
                colspan = 1

            c = colours[style]
            btn = tk.Button(
                self.root, text=label,
                font=('Helvetica', 22, 'bold'),
                bg=c['bg'], fg=c['fg'],
                activebackground=c['abg'], activeforeground=c['fg'],
                borderwidth=0, relief='flat',
                width=(8 if colspan == 2 else 4), height=2,
                command=lambda lbl=label: self._on_button(lbl)
            )
            btn.grid(row=row, column=col, columnspan=colspan,
                     padx=2, pady=2, sticky='ew')

    def _on_button(self, label: str):
        e = self.engine
        if label == 'AC':
            result = e.press_clear()
        elif label == '+/-':
            result = e.press_toggle_sign()
        elif label == '%':
            result = e.press_percent()
        elif label == '÷':
            result = e.press_operator('/')
        elif label == '×':
            result = e.press_operator('*')
        elif label in ('+', '-'):
            result = e.press_operator(label)
        elif label == '=':
            result = e.press_equals()
        elif label == '.':
            result = e.press_decimal()
        else:  # digit
            result = e.press_digit(label)
        self.display_var.set(result)

    def run(self):
        self.root.mainloop()
