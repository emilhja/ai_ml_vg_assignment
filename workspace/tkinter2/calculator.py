import tkinter as tk
from tkinter import font
import re


class Calculator:
    # Color constants
    COLOR_NUMBER = "#3498db"
    COLOR_OPERATOR = "#e74c3c"
    COLOR_SPECIAL = "#95a5a6"
    COLOR_EQUALS = "#27ae60"
    
    def __init__(self, root):
        self.root = root
        self.root.title("Calculator")
        self.root.geometry("400x500")
        self.root.resizable(False, False)
        
        # Variable to store the display text
        self.display_text = tk.StringVar()
        self.display_text.set("0")
        
        # Error state flag
        self.is_error = False
        
        # Create the display
        self.create_display()
        
        # Create the buttons
        self.create_buttons()
        
        # Bind keyboard events
        self.bind_keyboard()
    
    def create_display(self):
        """Create the display entry field"""
        display_frame = tk.Frame(self.root, bg="#2c3e50")
        display_frame.pack(fill=tk.BOTH, padx=10, pady=10)
        
        display_font = font.Font(family="Arial", size=24, weight="bold")
        
        display = tk.Entry(
            display_frame,
            textvariable=self.display_text,
            font=display_font,
            justify="right",
            bd=2,
            relief=tk.SUNKEN,
            bg="#ecf0f1",
            fg="#2c3e50",
            state="readonly",
            readonlybackground="#ecf0f1"
        )
        display.pack(fill=tk.BOTH, ipady=20)
        self.display = display
    
    def create_buttons(self):
        """Create all calculator buttons"""
        button_frame = tk.Frame(self.root, bg="#34495e")
        button_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Define button layout
        buttons = [
            ["C", "⌫", "/", "*"],
            ["7", "8", "9", "-"],
            ["4", "5", "6", "+"],
            ["1", "2", "3", "="],
            ["0", "0", ".", "="],
        ]
        
        # Create shared font for buttons
        button_font = font.Font(family="Arial", size=18, weight="bold")
        
        for row_idx, row in enumerate(buttons):
            for col_idx, btn_text in enumerate(row):
                # Skip duplicate cells for wide buttons
                if btn_text == "0" and col_idx == 1 and row_idx == 4:
                    continue
                
                # Determine button color and command
                if btn_text == "C":
                    bg_color = self.COLOR_SPECIAL
                    cmd = self.clear_display
                elif btn_text == "⌫":
                    bg_color = self.COLOR_SPECIAL
                    cmd = self.backspace
                elif btn_text == "=":
                    bg_color = self.COLOR_EQUALS
                    cmd = self.evaluate
                elif btn_text in ["+", "-", "*", "/"]:
                    bg_color = self.COLOR_OPERATOR
                    cmd = lambda op=btn_text: self.append_operator(op)
                elif btn_text == ".":
                    bg_color = self.COLOR_NUMBER
                    cmd = self.append_decimal
                else:
                    bg_color = self.COLOR_NUMBER
                    cmd = lambda digit=btn_text: self.append_digit(digit)
                
                # Create button
                button = tk.Button(
                    button_frame,
                    text=btn_text,
                    font=button_font,
                    bg=bg_color,
                    fg="white",
                    bd=0,
                    relief=tk.RAISED,
                    activebackground="#2c3e50",
                    activeforeground="white",
                    command=cmd
                )
                
                # Handle grid placement
                if btn_text == "0" and col_idx == 0 and row_idx == 4:
                    # Make "0" button span 2 columns
                    button.grid(row=row_idx, column=col_idx, columnspan=2, sticky="nsew", padx=5, pady=5)
                else:
                    button.grid(row=row_idx, column=col_idx, sticky="nsew", padx=5, pady=5)
        
        # Configure grid weights for proper expansion
        for i in range(5):
            button_frame.grid_rowconfigure(i, weight=1)
        for i in range(4):
            button_frame.grid_columnconfigure(i, weight=1)
    
    def bind_keyboard(self):
        """Bind keyboard keys to calculator actions"""
        for digit in '0123456789':
            self.root.bind(digit, lambda e, d=digit: self.append_digit(d))
        for op in ('+', '-', '*', '/'):
            self.root.bind(op, lambda e, o=op: self.append_operator(o))
        self.root.bind('.', lambda e: self.append_decimal())
        self.root.bind('<Return>', lambda e: self.evaluate())
        self.root.bind('=', lambda e: self.evaluate())
        self.root.bind('<BackSpace>', lambda e: self.backspace())
        self.root.bind('<Escape>', lambda e: self.clear_display())
        self.root.bind('c', lambda e: self.clear_display())
        self.root.bind('C', lambda e: self.clear_display())
    
    def append_digit(self, digit):
        """Append a digit to the display"""
        if self.is_error:
            self.is_error = False
            self.display_text.set(digit)
        else:
            current = self.display_text.get()
            if current == "0":
                self.display_text.set(digit)
            else:
                self.display_text.set(current + digit)
    
    def append_operator(self, operator):
        """Append an operator to the display"""
        if self.is_error:
            self.is_error = False
            self.display_text.set("0")
        current = self.display_text.get()
        if current and current[-1] not in ["+", "-", "*", "/"]:
            self.display_text.set(current + operator)
    
    def append_decimal(self):
        """Append a decimal point to the display"""
        if self.is_error:
            self.is_error = False
            self.display_text.set("0.")
            return
        current = self.display_text.get()
        # Split on operators to get the last token
        last_token = re.split(r'[+\-*/]', current)[-1]
        if '.' not in last_token:
            self.display_text.set(current + '.')
    
    def clear_display(self):
        """Clear the display"""
        self.display_text.set("0")
    
    def backspace(self):
        """Delete the last character from the display"""
        current = self.display_text.get()
        if len(current) > 1:
            self.display_text.set(current[:-1])
        else:
            self.display_text.set("0")
    
    def evaluate(self):
        """Evaluate the expression and display the result"""
        current = self.display_text.get()
        try:
            result = eval(current)
            self.display_text.set(str(result))
        except ZeroDivisionError:
            self.is_error = True
            self.display_text.set("Error")
        except Exception:
            self.is_error = True
            self.display_text.set("Error")


def main():
    root = tk.Tk()
    calculator = Calculator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
