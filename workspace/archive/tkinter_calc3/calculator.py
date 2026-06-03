import tkinter as tk
from tkinter import font


class Calculator:
    def __init__(self, root):
        self.root = root
        self.root.title("Calculator")
        self.root.geometry("400x500")
        self.root.resizable(False, False)
        
        self.display_var = tk.StringVar(value="0")
        self.current_expression = ""
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create the display and button grid."""
        # Display
        display_font = font.Font(family="Helvetica", size=24, weight="bold")
        display = tk.Entry(
            self.root,
            textvariable=self.display_var,
            font=display_font,
            justify="right",
            state="readonly",
            bd=2,
            relief="sunken"
        )
        display.grid(row=0, column=0, columnspan=4, padx=10, pady=20, sticky="nsew", ipady=10)
        
        # Button layout
        buttons = [
            ["C", "/", "*", "-"],
            ["7", "8", "9", "+"],
            ["4", "5", "6", "="],
            ["1", "2", "3", "="],
            ["0", ".", "00", "="],
        ]
        
        button_font = font.Font(family="Helvetica", size=18, weight="bold")
        
        for row_idx, row in enumerate(buttons, start=1):
            for col_idx, btn_text in enumerate(row):
                if btn_text == "=":
                    # Equals button spans multiple rows on the right
                    if row_idx == 1 or row_idx == 4 or row_idx == 5:
                        continue
                    btn = tk.Button(
                        self.root,
                        text=btn_text,
                        font=button_font,
                        command=self._on_equals,
                        bg="#4CAF50",
                        fg="white",
                        activebackground="#45a049"
                    )
                    btn.grid(row=row_idx, column=col_idx, padx=5, pady=5, sticky="nsew")
                elif btn_text == "C":
                    btn = tk.Button(
                        self.root,
                        text=btn_text,
                        font=button_font,
                        command=self._on_clear,
                        bg="#f44336",
                        fg="white",
                        activebackground="#da190b"
                    )
                    btn.grid(row=row_idx, column=col_idx, padx=5, pady=5, sticky="nsew")
                elif btn_text in ["+", "-", "*", "/"]:
                    btn = tk.Button(
                        self.root,
                        text=btn_text,
                        font=button_font,
                        command=lambda op=btn_text: self._on_operator(op),
                        bg="#FF9800",
                        fg="white",
                        activebackground="#e68900"
                    )
                    btn.grid(row=row_idx, column=col_idx, padx=5, pady=5, sticky="nsew")
                else:
                    btn = tk.Button(
                        self.root,
                        text=btn_text,
                        font=button_font,
                        command=lambda digit=btn_text: self._on_digit(digit),
                        bg="#2196F3",
                        fg="white",
                        activebackground="#0b7dda"
                    )
                    btn.grid(row=row_idx, column=col_idx, padx=5, pady=5, sticky="nsew")
        
        # Configure grid weights for responsive layout
        for i in range(1, 6):
            self.root.grid_rowconfigure(i, weight=1)
        for i in range(4):
            self.root.grid_columnconfigure(i, weight=1)
    
    def _on_digit(self, digit):
        """Handle digit button press."""
        current = self.display_var.get()
        
        if current == "0":
            if digit == ".":
                self.display_var.set("0.")
                self.current_expression = "0."
            elif digit == "00":
                # Don't add leading zeros
                pass
            else:
                self.display_var.set(digit)
                self.current_expression = digit
        else:
            # Handle decimal point
            if digit == ".":
                if "." not in current:
                    new_display = current + digit
                    self.display_var.set(new_display)
                    self.current_expression = new_display
            elif digit == "00":
                new_display = current + "00"
                self.display_var.set(new_display)
                self.current_expression = new_display
            else:
                new_display = current + digit
                self.display_var.set(new_display)
                self.current_expression = new_display
    
    def _on_operator(self, operator):
        """Handle operator button press."""
        current = self.display_var.get()
        
        # Prevent multiple consecutive operators or operator at start
        if current == "0" or current == "":
            return
        
        # Check if expression already ends with an operator
        if current[-1] in ["+", "-", "*", "/"]:
            return
        
        new_display = current + operator
        self.display_var.set(new_display)
        self.current_expression = new_display
    
    def _on_equals(self):
        """Handle equals button press."""
        expression = self.display_var.get()
        
        try:
            # Evaluate the expression
            result = eval(expression)
            result_str = str(result)
            
            # Handle very long decimals
            if "." in result_str:
                result_float = float(result)
                result_str = f"{result_float:.10g}"
            
            self.display_var.set(result_str)
            self.current_expression = result_str
        except ZeroDivisionError:
            self.display_var.set("Error")
            self.current_expression = "0"
        except Exception:
            self.display_var.set("Error")
            self.current_expression = "0"
    
    def _on_clear(self):
        """Handle clear button press."""
        self.display_var.set("0")
        self.current_expression = "0"


def main():
    root = tk.Tk()
    calc = Calculator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
