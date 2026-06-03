import tkinter as tk
from tkinter import font


class Calculator:
    def __init__(self, root):
        self.root = root
        self.root.title("Calculator")
        self.root.geometry("400x500")
        self.root.resizable(False, False)
        
        # Configure style
        self.root.configure(bg="#2b2b2b")
        
        # Expression string to build up the calculation
        self.expression = ""
        self.should_reset_display = False
        
        # Create GUI elements
        self.create_display()
        self.create_buttons()
        
        # Bind keyboard events
        self.root.bind("<Key>", self.on_key_press)
    
    def create_display(self):
        """Create the display/entry field"""
        display_frame = tk.Frame(self.root, bg="#2b2b2b")
        display_frame.pack(pady=10, padx=10, fill=tk.BOTH)
        
        self.display = tk.Entry(
            display_frame,
            font=("Arial", 20),
            borderwidth=2,
            relief=tk.FLAT,
            bg="#1e1e1e",
            fg="#00ff00",
            justify=tk.RIGHT
        )
        self.display.pack(fill=tk.BOTH, ipady=10)
        self.display.insert(0, "0")
    
    def create_buttons(self):
        """Create all calculator buttons"""
        button_frame = tk.Frame(self.root, bg="#2b2b2b")
        button_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        
        # Button layout
        buttons = [
            ["C", "⌫", "%", "/"],
            ["7", "8", "9", "*"],
            ["4", "5", "6", "-"],
            ["1", "2", "3", "+"],
            ["0", ".", "=", ""],
        ]
        
        for row_idx, row in enumerate(buttons):
            for col_idx, button_text in enumerate(row):
                if button_text == "":
                    continue
                
                button = tk.Button(
                    button_frame,
                    text=button_text,
                    font=("Arial", 18),
                    borderwidth=1,
                    relief=tk.RAISED,
                    command=lambda x=button_text: self.on_button_click(x)
                )
                
                # Styling for different button types
                if button_text == "=":
                    button.configure(bg="#00aa00", fg="white", activebackground="#00cc00")
                    button.grid(row=row_idx, column=col_idx, sticky="nsew", padx=5, pady=5, columnspan=2)
                elif button_text == "C":
                    button.configure(bg="#cc0000", fg="white", activebackground="#ff0000")
                    button.grid(row=row_idx, column=col_idx, sticky="nsew", padx=5, pady=5)
                elif button_text in ["+", "-", "*", "/", "%", "⌫"]:
                    button.configure(bg="#ff8800", fg="white", activebackground="#ffaa00")
                    button.grid(row=row_idx, column=col_idx, sticky="nsew", padx=5, pady=5)
                else:
                    button.configure(bg="#444444", fg="white", activebackground="#666666")
                    button.grid(row=row_idx, column=col_idx, sticky="nsew", padx=5, pady=5)
        
        # Configure grid weights for proper expansion
        for i in range(5):
            button_frame.grid_rowconfigure(i, weight=1)
        for i in range(4):
            button_frame.grid_columnconfigure(i, weight=1)
    
    def on_button_click(self, button_text):
        """Handle button clicks"""
        if button_text == "C":
            self.expression = ""
            self.display.delete(0, tk.END)
            self.display.insert(0, "0")
            self.should_reset_display = False
        
        elif button_text == "⌫":
            # Backspace: delete last character
            current = self.display.get()
            if len(current) > 1:
                self.display.delete(0, tk.END)
                self.display.insert(0, current[:-1])
                self.expression = current[:-1]
            else:
                self.display.delete(0, tk.END)
                self.display.insert(0, "0")
                self.expression = ""
            self.should_reset_display = False
        
        elif button_text == "=":
            self.evaluate_expression()
        
        elif button_text in ["+", "-", "*", "/", "%"]:
            current = self.display.get()
            if current != "0" or self.expression:
                if self.should_reset_display:
                    self.expression = current + button_text
                    self.should_reset_display = False
                else:
                    self.expression = current + button_text
                self.display.delete(0, tk.END)
                self.display.insert(0, "0")
        
        elif button_text == ".":
            current = self.display.get()
            if "." not in current:
                if self.should_reset_display:
                    self.display.delete(0, tk.END)
                    self.display.insert(0, "0.")
                    self.should_reset_display = False
                else:
                    self.display.delete(0, tk.END)
                    self.display.insert(0, current + ".")
        
        else:
            # Digit button
            current = self.display.get()
            if self.should_reset_display:
                self.display.delete(0, tk.END)
                self.display.insert(0, button_text)
                self.should_reset_display = False
            else:
                if current == "0":
                    self.display.delete(0, tk.END)
                    self.display.insert(0, button_text)
                else:
                    self.display.insert(tk.END, button_text)
    
    def evaluate_expression(self):
        """Evaluate the mathematical expression"""
        try:
            current = self.display.get()
            full_expression = self.expression + current
            
            # Handle percentage
            if "%" in full_expression:
                # Simple percentage handling: convert x% to x/100
                full_expression = full_expression.replace("%", "/100")
            
            result = eval(full_expression)
            
            # Round to avoid floating point display issues
            if isinstance(result, float):
                result = round(result, 10)
            
            self.display.delete(0, tk.END)
            self.display.insert(0, str(result))
            self.expression = ""
            self.should_reset_display = True
        
        except ZeroDivisionError:
            self.display.delete(0, tk.END)
            self.display.insert(0, "Error")
            self.expression = ""
            self.should_reset_display = True
        
        except:
            self.display.delete(0, tk.END)
            self.display.insert(0, "Error")
            self.expression = ""
            self.should_reset_display = True
    
    def on_key_press(self, event):
        """Handle keyboard input"""
        key = event.char
        
        # Digit keys
        if key in "0123456789":
            self.on_button_click(key)
        
        # Operation keys
        elif key == "+":
            self.on_button_click("+")
        elif key == "-":
            self.on_button_click("-")
        elif key == "*":
            self.on_button_click("*")
        elif key == "/":
            self.on_button_click("/")
        elif key == "%":
            self.on_button_click("%")
        
        # Decimal point
        elif key == ".":
            self.on_button_click(".")
        
        # Enter or equals
        elif key in ["\r", "="]:
            self.on_button_click("=")
        
        # Backspace
        elif event.keysym == "BackSpace":
            self.on_button_click("⌫")
        
        # Clear
        elif key.upper() == "C":
            self.on_button_click("C")


def main():
    root = tk.Tk()
    calculator = Calculator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
