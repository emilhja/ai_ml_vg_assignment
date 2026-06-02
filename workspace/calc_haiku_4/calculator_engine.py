class CalculatorEngine:
    """A calculator engine that handles digit input, operations, and evaluation."""
    
    def __init__(self):
        self.current_input = ""
        self.previous_input = ""
        self.operator = None
        self.result = None
        self.error = False
    
    def press_digit(self, digit: str) -> str:
        """Append digit to current_input, return display string."""
        if self.error:
            self.error = False
            self.current_input = digit
        else:
            self.current_input += digit
        return self.get_display()
    
    def press_decimal(self) -> str:
        """Append '.' if not already present, return display string."""
        if self.error:
            self.error = False
            self.current_input = "0."
        elif "." not in self.current_input:
            if not self.current_input:
                self.current_input = "0."
            else:
                self.current_input += "."
        return self.get_display()
    
    def press_operator(self, op: str) -> str:
        """Store operator, save current_input as previous_input, clear current_input."""
        if self.error:
            self.error = False
            self.current_input = ""
        
        if not self.current_input:
            self.current_input = "0"
        
        self.previous_input = self.current_input
        self.operator = op
        self.current_input = ""
        
        display = self.previous_input + op
        return display
    
    def press_equals(self) -> str:
        """Evaluate previous_input <op> current_input, store result, return display string."""
        if self.error:
            return "Error"
        
        if not self.operator or not self.previous_input:
            return self.get_display()
        
        if not self.current_input:
            self.current_input = "0"
        
        try:
            prev = float(self.previous_input)
            curr = float(self.current_input)
            
            if self.operator == "+":
                self.result = prev + curr
            elif self.operator == "-":
                self.result = prev - curr
            elif self.operator == "*":
                self.result = prev * curr
            elif self.operator == "/":
                if curr == 0:
                    self.error = True
                    self.operator = None
                    self.current_input = ""
                    self.previous_input = ""
                    return "Error"
                self.result = prev / curr
            
            result_str = str(int(self.result)) if self.result == int(self.result) else str(self.result)
            self.current_input = result_str
            self.previous_input = ""
            self.operator = None
            
            return result_str
        except ValueError:
            self.error = True
            return "Error"
    
    def press_clear(self) -> str:
        """Reset all state, return '0'."""
        self.current_input = ""
        self.previous_input = ""
        self.operator = None
        self.result = None
        self.error = False
        return "0"
    
    def press_toggle_sign(self) -> str:
        """Negate current_input, return display string."""
        if self.error:
            self.error = False
            self.current_input = ""
            return "0"
        
        if not self.current_input or self.current_input == "0":
            return "0"
        
        try:
            value = float(self.current_input)
            value = -value
            self.current_input = str(int(value)) if value == int(value) else str(value)
        except ValueError:
            pass
        
        return self.get_display()
    
    def press_percent(self) -> str:
        """Divide current_input by 100, return display string."""
        if self.error:
            self.error = False
            self.current_input = ""
            return "0"
        
        if not self.current_input:
            return "0"
        
        try:
            value = float(self.current_input)
            value = value / 100
            self.current_input = str(int(value)) if value == int(value) else str(value)
        except ValueError:
            pass
        
        return self.get_display()
    
    def get_display(self) -> str:
        """Return current display string."""
        if self.error:
            return "Error"
        
        if not self.current_input:
            return "0"
        
        return self.current_input
