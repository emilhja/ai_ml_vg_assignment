import tkinter as tk


class Calculator:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Calculator")
        self.root.geometry("400x500")
        self.root.resizable(False, False)
        
        self.display_var = tk.StringVar(value="0")
        self.current_input = ""
        self.operation = None
        self.first_number = None
        
        self.create_display()
        self.create_buttons()
    
    def create_display(self):
        """Create the display screen for the calculator."""
        display_frame = tk.Frame(self.root, bg="black", height=100)
        display_frame.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=5, pady=10)
        display_frame.grid_propagate(False)
        
        display = tk.Label(
            display_frame,
            textvariable=self.display_var,
            font=("Arial", 32, "bold"),
            bg="black",
            fg="white",
            anchor="e",
            padx=10,
            pady=20
        )
        display.pack(fill="both", expand=True)
    
    def create_buttons(self):
        """Create all calculator buttons in a grid layout."""
        # Button layout
        buttons = [
            ("C", 1, 0, 3, self.clear),
            ("/", 1, 3, 1, lambda: self.set_operation("/")),
            ("7", 2, 0, 1, lambda: self.append_digit("7")),
            ("8", 2, 1, 1, lambda: self.append_digit("8")),
            ("9", 2, 2, 1, lambda: self.append_digit("9")),
            ("*", 2, 3, 1, lambda: self.set_operation("*")),
            ("4", 3, 0, 1, lambda: self.append_digit("4")),
            ("5", 3, 1, 1, lambda: self.append_digit("5")),
            ("6", 3, 2, 1, lambda: self.append_digit("6")),
            ("-", 3, 3, 1, lambda: self.set_operation("-")),
            ("1", 4, 0, 1, lambda: self.append_digit("1")),
            ("2", 4, 1, 1, lambda: self.append_digit("2")),
            ("3", 4, 2, 1, lambda: self.append_digit("3")),
            ("+", 4, 3, 1, lambda: self.set_operation("+")),
            ("0", 5, 0, 2, lambda: self.append_digit("0")),
            (".", 5, 2, 1, lambda: self.append_digit(".")),
            ("=", 5, 3, 1, self.calculate),
        ]
        
        # Define button colors
        operation_color = "#FF9500"
        equals_color = "#4CAF50"
        clear_color = "#F44336"
        default_color = "#E0E0E0"
        
        for (text, row, col, colspan, command) in buttons:
            # Determine button color
            if text == "C":
                bg_color = clear_color
                fg_color = "white"
            elif text == "=":
                bg_color = equals_color
                fg_color = "white"
            elif text in ["+", "-", "*", "/"]:
                bg_color = operation_color
                fg_color = "white"
            else:
                bg_color = default_color
                fg_color = "black"
            
            button = tk.Button(
                self.root,
                text=text,
                font=("Arial", 20, "bold"),
                bg=bg_color,
                fg=fg_color,
                command=command,
                relief="raised",
                bd=2
            )
            button.grid(row=row, column=col, columnspan=colspan, sticky="nsew", padx=2, pady=2)
        
        # Configure row and column weights for proper expansion
        for i in range(1, 6):
            self.root.grid_rowconfigure(i, weight=1)
        for i in range(4):
            self.root.grid_columnconfigure(i, weight=1)
    
    def append_digit(self, digit):
        """Append a digit or decimal point to the current input."""
        if digit == ".":
            if "." not in self.current_input and self.current_input != "":
                self.current_input += digit
            elif self.current_input == "":
                self.current_input = "0."
        else:
            if self.current_input == "0":
                self.current_input = digit
            else:
                self.current_input += digit
        
        self.display_var.set(self.current_input)
    
    def set_operation(self, op):
        """Set the operation to perform."""
        if self.current_input != "":
            self.first_number = float(self.current_input)
            self.operation = op
            self.current_input = ""
            self.display_var.set(op)
    
    def calculate(self):
        """Calculate the result of the operation."""
        if self.operation is None or self.current_input == "":
            return
        
        try:
            second_number = float(self.current_input)
            
            if self.operation == "+":
                result = self.first_number + second_number
            elif self.operation == "-":
                result = self.first_number - second_number
            elif self.operation == "*":
                result = self.first_number * second_number
            elif self.operation == "/":
                if second_number == 0:
                    self.display_var.set("Error")
                    self.current_input = ""
                    self.operation = None
                    self.first_number = None
                    return
                result = self.first_number / second_number
            
            # Format result to remove unnecessary decimals
            if result == int(result):
                result = int(result)
            
            self.display_var.set(str(result))
            self.current_input = str(result)
            self.operation = None
            self.first_number = None
        
        except ValueError:
            self.display_var.set("Error")
            self.current_input = ""
            self.operation = None
            self.first_number = None
    
    def clear(self):
        """Clear all values and reset the calculator."""
        self.current_input = ""
        self.operation = None
        self.first_number = None
        self.display_var.set("0")


if __name__ == "__main__":
    root = tk.Tk()
    calculator = Calculator(root)
    root.mainloop()
