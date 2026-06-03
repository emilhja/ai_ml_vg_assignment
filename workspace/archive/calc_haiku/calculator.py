import tkinter as tk
from tkinter import font


class Calculator:
    def __init__(self, root):
        self.root = root
        self.root.title("Calculator")
        self.root.geometry("320x480")
        self.root.resizable(False, False)
        
        # Colour scheme
        self.bg_dark = "#1e1e1e"
        self.bg_light = "#2d2d2d"
        self.fg_text = "#ffffff"
        self.color_operator = "#ff9500"
        self.color_equals = "#4caf50"
        self.color_clear = "#f44336"
        self.color_digit = "#3d3d3d"
        
        self.root.config(bg=self.bg_dark)
        
        # Expression tracking
        self.expression = ""
        self.last_operator_pos = -1
        
        # Create display
        self.display_var = tk.StringVar(value="0")
        self.create_display()
        
        # Create button grid
        self.create_buttons()
    
    def create_display(self):
        display_frame = tk.Frame(self.root, bg=self.bg_light, height=80)
        display_frame.pack(fill=tk.BOTH, padx=10, pady=10)
        display_frame.pack_propagate(False)
        
        display_label = tk.Label(
            display_frame,
            textvariable=self.display_var,
            bg=self.bg_light,
            fg=self.fg_text,
            font=("Arial", 32, "bold"),
            anchor="e",
            justify=tk.RIGHT
        )
        display_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    def create_buttons(self):
        button_frame = tk.Frame(self.root, bg=self.bg_dark)
        button_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Button layout
        buttons = [
            ["C", "/", "×", "←"],
            ["7", "8", "9", "−"],
            ["4", "5", "6", "+"],
            ["1", "2", "3", "="],
            ["0", ".", ".", "="],
        ]
        
        for row_idx, row in enumerate(buttons):
            button_frame.grid_rowconfigure(row_idx, weight=1)
        
        for col_idx in range(4):
            button_frame.grid_columnconfigure(col_idx, weight=1)
        
        for row_idx, row in enumerate(buttons):
            for col_idx, label in enumerate(row):
                self.create_button(button_frame, label, row_idx, col_idx)
    
    def create_button(self, parent, label, row, col):
        # Determine button styling
        if label == "C":
            bg_color = self.color_clear
            fg_color = self.fg_text
            command = self.clear
        elif label == "←":
            bg_color = self.color_clear
            fg_color = self.fg_text
            command = self.backspace
        elif label in ["/", "×", "−", "+"]:
            bg_color = self.color_operator
            fg_color = self.fg_text
            command = lambda: self.append_operator(label)
        elif label == "=":
            bg_color = self.color_equals
            fg_color = self.fg_text
            command = self.evaluate
        else:
            bg_color = self.color_digit
            fg_color = self.fg_text
            command = lambda: self.append_value(label)
        
        # Skip duplicate decimal point button
        if label == "." and col == 2 and row == 4:
            return
        
        button = tk.Button(
            parent,
            text=label,
            bg=bg_color,
            fg=fg_color,
            font=("Arial", 18, "bold"),
            command=command,
            activebackground="#333333",
            activeforeground=self.fg_text,
            border=0,
            highlightthickness=0
        )
        
        # Make equals button span two columns on the last row
        if label == "=" and row == 4:
            button.grid(row=row, column=col, columnspan=2, sticky="nsew", padx=2, pady=2)
        else:
            button.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)
    
    def append_value(self, value):
        if value == ".":
            # Prevent multiple decimal points in the current number
            current_number = self.get_current_number()
            if "." in current_number:
                return
            if not current_number:
                self.expression += "0"
        
        self.expression += value
        self.update_display()
    
    def append_operator(self, operator):
        if not self.expression:
            return
        
        # Replace unicode operators with math symbols
        operator_map = {
            "×": "*",
            "−": "-",
            "+": "+",
            "/": "/"
        }
        
        # Remove trailing operator if present
        if self.expression and self.expression[-1] in "+-*/":
            self.expression = self.expression[:-1]
        
        self.expression += operator_map.get(operator, operator)
        self.update_display()
    
    def get_current_number(self):
        # Get the number being currently typed
        if not self.expression:
            return ""
        
        for i in range(len(self.expression) - 1, -1, -1):
            if self.expression[i] in "+-*/":
                return self.expression[i+1:]
        
        return self.expression
    
    def clear(self):
        self.expression = ""
        self.display_var.set("0")
    
    def backspace(self):
        self.expression = self.expression[:-1]
        self.update_display()
    
    def update_display(self):
        if not self.expression:
            self.display_var.set("0")
        else:
            # Display with unicode operators for readability
            display_text = self.expression
            display_text = display_text.replace("*", "×")
            display_text = display_text.replace("-", "−")
            self.display_var.set(display_text)
    
    def evaluate(self):
        if not self.expression:
            return
        
        try:
            # Evaluate the expression
            result = eval(self.expression)
            
            # Format result to avoid excessive decimals
            if isinstance(result, float):
                if result == int(result):
                    self.expression = str(int(result))
                else:
                    self.expression = f"{result:.10g}"
            else:
                self.expression = str(result)
            
            self.update_display()
        except ZeroDivisionError:
            self.display_var.set("Error: Division by zero")
            self.expression = ""
        except Exception as e:
            self.display_var.set("Error: Invalid expression")
            self.expression = ""


def main():
    root = tk.Tk()
    calculator = Calculator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
