import tkinter as tk
from calc_haiku_3.calculator_engine import CalculatorEngine


class CalculatorApp(tk.Frame):
    """Tkinter UI for a simple calculator."""
    
    def __init__(self, master=None):
        super().__init__(master)
        self.engine = CalculatorEngine()
        self._build_ui()
    
    def _build_ui(self):
        """Build the calculator UI with display and button grid."""
        # Display label for current number/result
        self.display_label = tk.Label(
            self,
            text=self.engine.get_display(),
            font=("Arial", 28),
            anchor="e",
            bg="#222",
            fg="white",
            height=2
        )
        self.display_label.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=5, pady=5)
        
        # Expression label for ongoing calculation
        self.expr_label = tk.Label(
            self,
            text=self.engine.get_expression(),
            font=("Arial", 12),
            anchor="e",
            bg="#222",
            fg="#aaa"
        )
        self.expr_label.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=5, pady=2)
        
        # Button layout
        button_rows = [
            ['C', '←', '%', '/'],
            ['7', '8', '9', '*'],
            ['4', '5', '6', '-'],
            ['1', '2', '3', '+'],
            ['0', '.', '+/-', '=']
        ]
        
        # Define button colors
        operator_buttons = {'/', '*', '-', '+', '='}
        utility_buttons = {'C', '←', '%'}
        digit_buttons = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '.'}
        
        # Create buttons
        self.buttons = {}
        for row_idx, row in enumerate(button_rows, start=2):
            for col_idx, char in enumerate(row):
                if char in operator_buttons:
                    bg_color = "#FF9500"
                    fg_color = "white"
                elif char in utility_buttons:
                    bg_color = "#a5a5a5"
                    fg_color = "black"
                else:  # digit and decimal
                    bg_color = "#333"
                    fg_color = "white"
                
                btn = tk.Button(
                    self,
                    text=char,
                    font=("Arial", 18),
                    bg=bg_color,
                    fg=fg_color,
                    padx=18,
                    pady=18,
                    relief=tk.FLAT,
                    cursor="hand2",
                    command=lambda c=char: self._handle_button(c)
                )
                btn.grid(row=row_idx, column=col_idx, sticky="nsew", padx=2, pady=2)
                self.buttons[char] = btn
        
        # Bind keyboard events
        self.bind("<Key>", self._on_key)
    
    def _handle_button(self, char):
        """Handle button press."""
        if char in "0123456789":
            self.engine.append_digit(char)
        elif char == ".":
            self.engine.append_digit(".")
        elif char in "+-*/%=":
            if char == "=":
                self.engine.calculate()
            else:
                self.engine.set_operator(char)
        elif char == "C":
            self.engine.clear()
        elif char == "←":
            self.engine.backspace()
        elif char == "%":
            # Divide current_input by 100
            if self.engine.current_input:
                try:
                    value = float(self.engine.current_input) / 100
                    self.engine.current_input = str(value)
                except ValueError:
                    pass
        elif char == "+/-":
            # Negate current_input
            if self.engine.current_input:
                if self.engine.current_input.startswith("-"):
                    self.engine.current_input = self.engine.current_input[1:]
                else:
                    self.engine.current_input = "-" + self.engine.current_input
        
        self._refresh()
    
    def _on_key(self, event):
        """Handle keyboard input."""
        char = event.char
        
        if char in "0123456789":
            self._handle_button(char)
        elif char in "+-*/.":
            self._handle_button(char)
        elif event.keysym == "Return":
            self._handle_button("=")
        elif event.keysym == "BackSpace":
            self._handle_button("←")
        elif event.keysym == "Escape":
            self._handle_button("C")
    
    def _refresh(self):
        """Update display and expression labels."""
        self.display_label.config(text=self.engine.get_display())
        self.expr_label.config(text=self.engine.get_expression())
