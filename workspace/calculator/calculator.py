"""
Simple Calculator Application using tkinter.
Supports basic arithmetic operations with keyboard and GUI input.
"""

import tkinter as tk
from tkinter import font


class Calculator:
    """A simple calculator application with tkinter GUI."""

    def __init__(self, root):
        """Initialize the calculator with the main window."""
        self.root = root
        self.root.title("Calculator")
        self.root.geometry("400x500")
        self.root.resizable(False, False)

        self.expression = ""
        self.result_var = tk.StringVar(value="0")
        self.just_evaluated = False

        # Set up colors
        self.bg_color = "#2c3e50"
        self.display_bg = "#34495e"
        self.button_bg = "#3498db"
        self.operator_bg = "#e74c3c"
        self.equals_bg = "#27ae60"
        self.clear_bg = "#e67e22"
        self.text_color = "#ecf0f1"

        self.root.configure(bg=self.bg_color)

        self._create_widgets()
        self._bind_keys()

    def _create_widgets(self):
        """Create the GUI widgets."""
        # Display frame
        display_frame = tk.Frame(self.root, bg=self.bg_color)
        display_frame.pack(pady=10, padx=10, fill=tk.BOTH)

        # Display entry
        self.display = tk.Entry(
            display_frame,
            textvariable=self.result_var,
            font=("Arial", 28, "bold"),
            bg=self.display_bg,
            fg=self.text_color,
            border=2,
            justify=tk.RIGHT,
            state="readonly",
        )
        self.display.pack(fill=tk.BOTH, expand=True, ipady=15)

        # Buttons frame
        buttons_frame = tk.Frame(self.root, bg=self.bg_color)
        buttons_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        # Define button layout: Row 0: C ⌫ % /, Row 1: 7 8 9 *, Row 2: 4 5 6 -, Row 3: 1 2 3 +, Row 4: 0(colspan=2) . =
        buttons = [
            ["C", "⌫", "%", "/"],
            ["7", "8", "9", "*"],
            ["4", "5", "6", "-"],
            ["1", "2", "3", "+"],
            ["0", ".", "="],
        ]

        # Button colors and commands
        self.button_commands = {
            "0": lambda: self._append_digit("0"),
            "1": lambda: self._append_digit("1"),
            "2": lambda: self._append_digit("2"),
            "3": lambda: self._append_digit("3"),
            "4": lambda: self._append_digit("4"),
            "5": lambda: self._append_digit("5"),
            "6": lambda: self._append_digit("6"),
            "7": lambda: self._append_digit("7"),
            "8": lambda: self._append_digit("8"),
            "9": lambda: self._append_digit("9"),
            ".": lambda: self._append_digit("."),
            "+": lambda: self._append_operator("+"),
            "-": lambda: self._append_operator("-"),
            "*": lambda: self._append_operator("*"),
            "/": lambda: self._append_operator("/"),
            "%": lambda: self._append_operator("%"),
            "=": self._evaluate,
            "C": self._clear,
            "⌫": self._backspace,
        }

        # Create buttons
        for row_idx, row in enumerate(buttons):
            for col_idx, label in enumerate(row):
                # Determine button color
                if label == "C":
                    btn_bg = self.clear_bg
                elif label == "⌫":
                    btn_bg = self.clear_bg
                elif label in ["+", "-", "*", "/", "%"]:
                    btn_bg = self.operator_bg
                elif label == "=":
                    btn_bg = self.equals_bg
                else:
                    btn_bg = self.button_bg

                button = tk.Button(
                    buttons_frame,
                    text=label,
                    font=("Arial", 18, "bold"),
                    bg=btn_bg,
                    fg=self.text_color,
                    border=2,
                    command=self.button_commands.get(label),
                    padx=20,
                    pady=20,
                    activebackground="#2980b9" if label not in ["C", "⌫"] else "#d35400",
                )

                # Handle "0" spanning two columns in row 4
                if label == "0" and row_idx == 4:
                    button.grid(row=row_idx, column=col_idx, columnspan=2, sticky="nsew", padx=2, pady=2)
                else:
                    button.grid(row=row_idx, column=col_idx, sticky="nsew", padx=2, pady=2)

        # Configure grid weights for resizing
        for i in range(5):
            buttons_frame.grid_rowconfigure(i, weight=1)
        for i in range(4):
            buttons_frame.grid_columnconfigure(i, weight=1)

    def _bind_keys(self):
        """Bind keyboard events."""
        self.root.bind("<Key>", self._on_key_press)
        self.root.bind("<Return>", lambda e: self._evaluate())
        self.root.bind("<BackSpace>", lambda e: self._backspace())
        self.root.bind("<Escape>", lambda e: self._clear())

    def _on_key_press(self, event):
        """Handle keyboard input."""
        key = event.char
        if key.isdigit():
            self._append_digit(key)
        elif key in ["+", "-", "*", "/", "%"]:
            self._append_operator(key)
        elif key == ".":
            self._append_digit(".")

    def _append_digit(self, digit):
        """Append a digit to the expression."""
        if self.just_evaluated:
            self.expression = digit
            self.just_evaluated = False
        elif self.result_var.get() == "0" and digit != ".":
            self.expression = digit
        elif self.result_var.get() == "Error":
            self.expression = digit
        else:
            self.expression += digit
        self.result_var.set(self.expression)

    def _append_operator(self, operator):
        """Append an operator to the expression."""
        if self.result_var.get() == "Error":
            return
        if self.just_evaluated:
            self.just_evaluated = False
        if self.expression and self.expression[-1] not in ["+", "-", "*", "/", "%"]:
            self.expression += operator
            self.result_var.set(self.expression)

    def _evaluate(self):
        """Evaluate the expression and display the result."""
        try:
            if not self.expression:
                return
            result = eval(self.expression)
            self.expression = str(result)
            self.result_var.set(self.expression)
            self.just_evaluated = True
        except Exception:
            self.result_var.set("Error")
            self.expression = ""

    def _clear(self):
        """Clear the display and reset the expression."""
        self.expression = ""
        self.result_var.set("0")
        self.just_evaluated = False

    def _backspace(self):
        """Delete the last character from the expression."""
        if self.result_var.get() == "Error":
            self._clear()
        else:
            self.expression = self.expression[:-1]
            self.result_var.set(self.expression if self.expression else "0")
            self.just_evaluated = False


def main():
    """Run the calculator application."""
    root = tk.Tk()
    app = Calculator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
