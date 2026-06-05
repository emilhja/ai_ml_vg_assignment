# Emil
import tkinter as tk
from tkinter import font


class Calculator:
    def __init__(self, root):
        self.root = root
        self.root.title("Calculator")
        self.root.geometry("400x500")
        self.root.resizable(False, False)
        
        # Variable to store the display content
        self.display_var = tk.StringVar(value="0")
        
        # Create UI
        self.create_widgets()
    
    def create_widgets(self):
        # Main frame
        main_frame = tk.Frame(self.root, bg="#2c3e50")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Display frame
        display_frame = tk.Frame(main_frame, bg="#2c3e50")
        display_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Display entry
        display_font = font.Font(family="Arial", size=20, weight="bold")
        self.display = tk.Entry(
            display_frame,
            textvariable=self.display_var,
            font=display_font,
            justify=tk.RIGHT,
            bg="#ecf0f1",
            fg="#2c3e50",
            bd=0,
            state="readonly"
        )
        self.display.pack(fill=tk.BOTH, padx=5, pady=5, ipady=15)
        
        # Buttons frame
        buttons_frame = tk.Frame(main_frame, bg="#2c3e50")
        buttons_frame.pack(fill=tk.BOTH, expand=True)
        
        # Define button layout
        buttons = [
            ["C", "⌫", "/", "*"],
            ["7", "8", "9", "-"],
            ["4", "5", "6", "+"],
            ["1", "2", "3", "."],
            ["0", "="]
        ]
        
        button_font = font.Font(family="Arial", size=16, weight="bold")
        
        # Create buttons
        for row_idx, row in enumerate(buttons):
            buttons_frame.grid_rowconfigure(row_idx, weight=1)
            for col_idx, btn_text in enumerate(row):
                # Calculate column span (0 spans 2 columns)
                colspan = 2 if btn_text == "0" else 1
                
                # Set grid weight for columns
                if col_idx == 0 or (col_idx > 0 and buttons[row_idx][col_idx - 1] != "0"):
                    buttons_frame.grid_columnconfigure(col_idx, weight=1)
                
                # Create button with appropriate color
                if btn_text == "=":
                    bg_color = "#27ae60"
                    fg_color = "#ecf0f1"
                elif btn_text in ["+", "-", "*", "/"]:
                    bg_color = "#e74c3c"
                    fg_color = "#ecf0f1"
                elif btn_text in ["C", "⌫"]:
                    bg_color = "#e67e22"
                    fg_color = "#ecf0f1"
                else:
                    bg_color = "#34495e"
                    fg_color = "#ecf0f1"
                
                btn = tk.Button(
                    buttons_frame,
                    text=btn_text,
                    font=button_font,
                    bg=bg_color,
                    fg=fg_color,
                    activebackground="#2c3e50",
                    activeforeground="#ecf0f1",
                    bd=0,
                    command=lambda t=btn_text: self.on_button_click(t)
                )
                btn.grid(
                    row=row_idx,
                    column=col_idx,
                    columnspan=colspan,
                    sticky="nsew",
                    padx=2,
                    pady=2
                )
    
    def on_button_click(self, char):
        current = self.display_var.get()
        
        if char == "C":
            # Clear display
            self.display_var.set("0")
        elif char == "⌫":
            # Backspace - remove last character
            if current == "0":
                return
            elif len(current) == 1:
                self.display_var.set("0")
            else:
                self.display_var.set(current[:-1])
        elif char == "=":
            # Evaluate expression
            try:
                result = eval(current)
                # Round to avoid floating point precision issues
                if isinstance(result, float):
                    result = round(result, 10)
                self.display_var.set(str(result))
            except (SyntaxError, ZeroDivisionError, NameError, TypeError):
                self.display_var.set("Error")
        elif char in ["+", "-", "*", "/"]:
            # Operator button
            if current == "0":
                self.display_var.set("0" + char)
            elif current.endswith((".", "+", "-", "*", "/")):
                # Replace last operator if it's an operator
                if current[-1] in ["+", "-", "*", "/"]:
                    self.display_var.set(current[:-1] + char)
                # Don't add operator after decimal or incomplete expression
            else:
                self.display_var.set(current + char)
        elif char == ".":
            # Decimal point
            if current == "0":
                self.display_var.set("0.")
            elif current.endswith((".", "+", "-", "*", "/")):
                # Don't add decimal if already exists or after operator
                pass
            else:
                # Check if current number (after last operator) already has decimal
                last_operator_idx = max(
                    current.rfind("+"),
                    current.rfind("-"),
                    current.rfind("*"),
                    current.rfind("/")
                )
                last_number = current[last_operator_idx + 1:]
                if "." not in last_number:
                    self.display_var.set(current + char)
        else:
            # Digit button
            if current == "0":
                self.display_var.set(char)
            else:
                self.display_var.set(current + char)


if __name__ == "__main__":
    root = tk.Tk()
    app = Calculator(root)
    root.mainloop()
