import tkinter as tk
from tkinter import font


class Calculator:
    def __init__(self, root):
        self.root = root
        self.root.title("Calculator")
        self.root.geometry("400x500")
        self.root.resizable(False, False)
        
        self.expression = ""
        self.result_var = tk.StringVar(value="0")
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the calculator user interface."""
        # Display frame
        display_frame = tk.Frame(self.root, bg="#2c3e50", pady=10)
        display_frame.pack(fill=tk.BOTH, expand=False)
        
        # Display screen
        display = tk.Entry(
            display_frame,
            textvariable=self.result_var,
            font=("Arial", 24, "bold"),
            bg="#34495e",
            fg="#ecf0f1",
            borderwidth=2,
            relief=tk.SOLID,
            justify=tk.RIGHT,
            state=tk.DISABLED
        )
        display.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Buttons frame
        buttons_frame = tk.Frame(self.root, bg="#2c3e50")
        buttons_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Button layout
        button_layout = [
            [("C", "#e74c3c"), ("⌫", "#e74c3c"), ("/", "#f39c12"), ("×", "#f39c12")],
            [("7", "#ecf0f1"), ("8", "#ecf0f1"), ("9", "#ecf0f1"), ("-", "#f39c12")],
            [("4", "#ecf0f1"), ("5", "#ecf0f1"), ("6", "#ecf0f1"), ("+", "#f39c12")],
            [("1", "#ecf0f1"), ("2", "#ecf0f1"), ("3", "#ecf0f1"), ("=", "#27ae60")],
            [("0", "#ecf0f1"), (".", "#ecf0f1")]
        ]
        
        # Create buttons
        for row_idx, row in enumerate(button_layout):
            row_frame = tk.Frame(buttons_frame, bg="#2c3e50")
            row_frame.pack(fill=tk.BOTH, expand=True)
            
            for col_idx, (text, color) in enumerate(row):
                btn = tk.Button(
                    row_frame,
                    text=text,
                    font=("Arial", 18, "bold"),
                    bg=color,
                    fg="black" if color == "#ecf0f1" else "#ecf0f1",
                    borderwidth=2,
                    relief=tk.RAISED,
                    activebackground=self.lighten_color(color),
                    command=lambda t=text: self.on_button_click(t)
                )
                
                # Special grid for 0 and . button (wider 0 button)
                if row_idx == 4:
                    if text == "0":
                        btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
                    else:
                        btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
                else:
                    btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
    
    def lighten_color(self, color):
        """Return a lighter shade of the given color for active state."""
        lightening = {
            "#ecf0f1": "#d5dbdb",
            "#e74c3c": "#ec7063",
            "#f39c12": "#f8b739",
            "#27ae60": "#52be80",
            "#f39c12": "#f8b739"
        }
        return lightening.get(color, color)
    
    def on_button_click(self, char):
        """Handle button click events."""
        if char == "C":
            self.clear()
        elif char == "⌫":
            self.backspace()
        elif char == "=":
            self.calculate()
        elif char == "×":
            self.add_operator("*")
        else:
            self.add_character(char)
    
    def add_character(self, char):
        """Add a character to the expression."""
        if self.result_var.get() == "Error":
            self.expression = ""
            self.result_var.set("0")
        
        if char == ".":
            # Prevent multiple decimals in the same number
            if "." not in self.get_current_number():
                if not self.expression or self.expression[-1] in "+-*/.":
                    self.expression += "0."
                else:
                    self.expression += "."
        else:
            if self.expression == "" and self.result_var.get() == "0":
                self.expression = char
            else:
                self.expression += char
        
        self.update_display()
    
    def add_operator(self, operator):
        """Add an operator to the expression."""
        if self.result_var.get() == "Error":
            self.expression = ""
            self.result_var.set("0")
        
        if self.expression and self.expression[-1] not in "+-*/.":
            self.expression += operator
            self.update_display()
    
    def get_current_number(self):
        """Get the current number being typed (after the last operator)."""
        for op in "+-*/.":
            self.expression = self.expression.replace(op, f" {op} ")
        parts = self.expression.split()
        return parts[-1] if parts else ""
    
    def backspace(self):
        """Remove the last character from the expression."""
        if self.result_var.get() == "Error":
            self.expression = ""
            self.result_var.set("0")
        else:
            self.expression = self.expression[:-1]
        
        self.update_display()
    
    def clear(self):
        """Clear the calculator."""
        self.expression = ""
        self.result_var.set("0")
    
    def update_display(self):
        """Update the display with the current expression."""
        if not self.expression:
            self.result_var.set("0")
        else:
            self.result_var.set(self.expression)
    
    def calculate(self):
        """Evaluate the expression and display the result."""
        try:
            if not self.expression:
                return
            
            # Replace × with * for evaluation
            eval_expr = self.expression.replace("×", "*")
            
            # Check for division by zero before evaluation
            if "/0" in eval_expr:
                self.result_var.set("Error: Div by 0")
                self.expression = ""
                return
            
            # Evaluate the expression
            result = eval(eval_expr)
            
            # Round to avoid floating point errors
            if isinstance(result, float):
                if result == int(result):
                    result = int(result)
                else:
                    result = round(result, 10)
            
            self.result_var.set(str(result))
            self.expression = str(result)
        
        except ZeroDivisionError:
            self.result_var.set("Error: Div by 0")
            self.expression = ""
        except SyntaxError:
            self.result_var.set("Error: Invalid")
            self.expression = ""
        except Exception as e:
            self.result_var.set("Error: Invalid")
            self.expression = ""


def main():
    root = tk.Tk()
    calculator = Calculator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
