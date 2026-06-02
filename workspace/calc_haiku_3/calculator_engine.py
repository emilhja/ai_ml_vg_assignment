class CalculatorEngine:
    """Pure calculation logic for a simple calculator."""
    
    def __init__(self):
        self.current_input = ''
        self.expression = ''
        self.result = '0'
        self.new_number = True
    
    def append_digit(self, digit: str) -> None:
        """Appends a digit or '.' to current_input, guarding against multiple dots."""
        if digit == '.':
            if '.' in self.current_input:
                return
            if not self.current_input:
                self.current_input = '0'
        
        self.current_input += digit
        self.new_number = False
    
    def set_operator(self, op: str) -> None:
        """Stores current_input into expression with the operator, resets current_input."""
        if self.current_input:
            self.expression += self.current_input + op
            self.current_input = ''
        elif self.expression and self.expression[-1] not in '+-*/%':
            # Replace the last operator if no new number was entered
            self.expression = self.expression[:-1] + op
        else:
            self.expression += op
        
        self.new_number = True
    
    def calculate(self) -> None:
        """Evaluates the full expression + current_input using eval, stores result, resets state."""
        if self.expression and self.current_input:
            try:
                full_expression = self.expression + self.current_input
                self.result = str(eval(full_expression))
                self.expression = ''
                self.current_input = ''
                self.new_number = True
            except Exception:
                self.result = 'Error'
                self.expression = ''
                self.current_input = ''
                self.new_number = True
    
    def clear(self) -> None:
        """Resets everything to initial state."""
        self.current_input = ''
        self.expression = ''
        self.result = '0'
        self.new_number = True
    
    def backspace(self) -> None:
        """Removes last character from current_input."""
        if self.current_input:
            self.current_input = self.current_input[:-1]
    
    def get_display(self) -> str:
        """Returns current_input if non-empty, else result."""
        return self.current_input if self.current_input else self.result
    
    def get_expression(self) -> str:
        """Returns expression string."""
        return self.expression
