import tkinter as tk
from tkinter import font


class Calculator:
    def __init__(self, root):
        self.root = root
        self.root.title("Calculator")
        self.root.geometry("400x500")
        self.root.resizable(False, False)
        
        # Expression tracking
        self.expression = ""
        self.result_value = 0
        
        # Define colors
        self.bg_color = "#f0f0f0"
        self.display_bg = "#2c3e50"
        self.display_fg = "#ecf0f1"
        self.button_bg = "#ecf0f1"
        self.button_fg = "#2c3e50"
        self.operator_bg = "#3498db"
        self.operator_fg = "#ffffff"
        self.equals_bg = "#27ae60"
        self.equals_fg = "#ffffff"
        self.clear_bg = "#e74c3c"
        self.clear_fg = "#ffffff"
        
        self.root.configure(bg=self.bg_color)
        
        # Create display
        self.create_display()
        
        # Create buttons
        self.create_buttons()
    
    def create_display(self):
        """Create the display screen for the calculator."""
        display_frame = tk.Frame(self.root, bg=self.display_bg, height=100)
        display_frame.pack(fill=tk.BOTH, padx=10, pady=10)
        display_frame.pack_propagate(False)
        
        self.display_var = tk.StringVar()
        self.display_var.set("0")
        
        display_font = font.Font(family="Arial", size=24, weight="bold")
        
        display_label = tk.Label(
            display_frame,
            textvariable=self.display_var,
            bg=self.display_bg,
            fg=self.display_fg,
            font=display_font,
            anchor="e",
            padx=20,
            pady=20
        )
        display_label.pack(fill=tk.BOTH, expand=True)
    
    def create_buttons(self):
        """Create calculator buttons in a grid layout."""
        button_frame = tk.Frame(self.root, bg=self.bg_color)
        button_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Button layout: (text, row, column, rowspan, colspan, bg, fg)
        button_layout = [
            ("C", 0, 0, 1, 1, self.clear_bg, self.clear_fg),
            ("/", 0, 1, 1, 1, self.operator_bg, self.operator_fg),
            ("*", 0, 2, 1, 1, self.operator_bg, self.operator_fg),
            ("-", 0, 3, 1, 1, self.operator_bg, self.operator_fg),
            
            ("7", 1, 0, 1, 1, self.button_bg, self.button_fg),
            ("8", 1, 1, 1, 1, self.button_bg, self.button_fg),
            ("9", 1, 2, 1, 1, self.button_bg, self.button_fg),
            ("+", 1, 3, 1, 1, self.operator_bg, self.operator_fg),
            
            ("4", 2, 0, 1, 1, self.button_bg, self.button_fg),
            ("5", 2, 1, 1, 1, self.button_bg, self.button_fg),
            ("6", 2, 2, 1, 1, self.button_bg, self.button_fg),
            (".", 2, 3, 1, 1, self.button_bg, self.button_fg),
            
            ("1", 3, 0, 1, 1, self.button_bg, self.button_fg),
            ("2", 3, 1, 1, 1, self.button_bg, self.button_fg),
            ("3", 3, 2, 1, 1, self.button_bg, self.button_fg),
            ("=", 3, 3, 1, 1, self.equals_bg, self.equals_fg),
            
            ("0", 4, 0, 1, 2, self.button_bg, self.button_fg),
        ]
        
        button_font = font.Font(family="Arial", size=16, weight="bold")
        
        for text, row, col, rowspan, colspan, bg, fg in button_layout:
            self.create_button(button_frame, text, row, col, rowspan, colspan, bg, fg, button_font)
    
    def create_button(self, parent, text, row, col, rowspan, colspan, bg, fg, button_font):
        """Create a single button and add it to the grid."""
        btn = tk.Button(
            parent,
            text=text,
            font=button_font,
            bg=bg,
            fg=fg,
            activebackground=bg,
            activeforeground=fg,
            relief=tk.RAISED,
            bd=2,
            command=lambda: self.on_button_click(text)
        )
        btn.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan, sticky="nsew", padx=5, pady=5)
    
    def configure_grid(self, parent):
        """Configure grid weights for uniform button sizing."""
        for i in range(5):
            parent.grid_rowconfigure(i, weight=1)
        for i in range(4):
            parent.grid_columnconfigure(i, weight=1)
    
    def on_button_click(self, char):
        """Handle button clicks."""
        if char == "C":
            self.clear()
        elif char == "=":
            self.calculate()
        elif char in "0123456789":
            self.append_digit(char)
        elif char in "+-*/.":
            self.append_operator(char)
    
    def append_digit(self, digit):
        """Append a digit to the expression."""
        current = self.display_var.get()
        
        # Replace initial "0" with the digit
        if current == "0" or current == "Error":
            self.expression = digit
        else:
            self.expression += digit
        
        self.display_var.set(self.expression)
    
    def append_operator(self, operator):
        """Append an operator to the expression."""
        current = self.display_var.get()
        
        # Don't add operator if expression is empty or ends with an operator
        if not self.expression or self.expression[-1] in "+-*/.":
            return
        
        self.expression += operator
        self.display_var.set(self.expression)
    
    def calculate(self):
        """Evaluate the expression and display the result."""
        if not self.expression:
            return
        
        try:
            # Evaluate the expression
            self.result_value = eval(self.expression)
            
            # Format the result
            if isinstance(self.result_value, float):
                # Remove trailing zeros and decimal point if not needed
                if self.result_value == int(self.result_value):
                    result_str = str(int(self.result_value))
                else:
                    result_str = f"{self.result_value:.10g}"
            else:
                result_str = str(self.result_value)
            
            self.display_var.set(result_str)
            self.expression = result_str
            
        except ZeroDivisionError:
            self.display_var.set("Error")
            self.expression = ""
        except Exception:
            self.display_var.set("Error")
            self.expression = ""
    
    def clear(self):
        """Clear the calculator."""
        self.expression = ""
        self.result_value = 0
        self.display_var.set("0")


def main():
    root = tk.Tk()
    calculator = Calculator(root)
    
    # Configure button frame grid weights
    button_frame = root.winfo_children()[1]
    for i in range(5):
        button_frame.grid_rowconfigure(i, weight=1)
    for i in range(4):
        button_frame.grid_columnconfigure(i, weight=1)
    
    root.mainloop()


if __name__ == "__main__":
    main()
