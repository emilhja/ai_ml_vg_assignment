"""
Calculator module with basic arithmetic operations and history tracking.
"""


class Calculator:
    """
    A simple calculator class that performs basic arithmetic operations.
    
    Attributes:
        history (list): A list of tuples recording each operation,
                       in the format (operation, operand1, operand2, result).
    """
    
    def __init__(self):
        """Initialize the calculator with an empty history."""
        self.history = []
    
    def add(self, a, b):
        """
        Add two numbers.
        
        Args:
            a (float): The first number.
            b (float): The second number.
            
        Returns:
            float: The sum of a and b.
        """
        result = a + b
        self._record_operation("add", a, b, result)
        return result
    
    def subtract(self, a, b):
        """
        Subtract b from a.
        
        Args:
            a (float): The first number (minuend).
            b (float): The second number (subtrahend).
            
        Returns:
            float: The difference (a - b).
        """
        result = a - b
        self._record_operation("subtract", a, b, result)
        return result
    
    def multiply(self, a, b):
        """
        Multiply two numbers.
        
        Args:
            a (float): The first number.
            b (float): The second number.
            
        Returns:
            float: The product of a and b.
        """
        result = a * b
        self._record_operation("multiply", a, b, result)
        return result
    
    def divide(self, a, b):
        """
        Divide a by b.
        
        Args:
            a (float): The dividend.
            b (float): The divisor.
            
        Returns:
            float: The quotient (a / b).
            
        Raises:
            ValueError: If b is zero (division by zero).
        """
        if b == 0:
            raise ValueError("Cannot divide by zero.")
        result = a / b
        self._record_operation("divide", a, b, result)
        return result
    
    def _record_operation(self, operation, a, b, result):
        """
        Record an operation in the history.
        
        Args:
            operation (str): The name of the operation.
            a (float): The first operand.
            b (float): The second operand.
            result (float): The result of the operation.
        """
        self.history.append((operation, a, b, result))
    
    def clear_history(self):
        """Clear the operation history."""
        self.history = []
    
    def show_history(self):
        """
        Display the operation history.
        
        Returns:
            str: A formatted string of the history, or a message if empty.
        """
        if not self.history:
            return "No history yet."
        
        lines = ["Operation History:"]
        for i, (op, a, b, result) in enumerate(self.history, start=1):
            lines.append(f"{i}. {a} {op} {b} = {result}")
        
        return "\n".join(lines)
