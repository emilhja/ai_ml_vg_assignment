#!/usr/bin/env python3
"""A simple terminal calculator that supports basic arithmetic operations."""


def add(a, b):
    """Add two numbers."""
    return a + b


def subtract(a, b):
    """Subtract two numbers."""
    return a - b


def multiply(a, b):
    """Multiply two numbers."""
    return a * b


def divide(a, b):
    """Divide two numbers. Raises ValueError if b is zero."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


def parse_input(user_input):
    """
    Parse user input into operand1, operator, operand2.
    
    Returns a tuple (operand1, operator, operand2) or None if parsing fails.
    """
    try:
        parts = user_input.strip().split()
        if len(parts) != 3:
            return None
        
        operand1 = float(parts[0])
        operator = parts[1]
        operand2 = float(parts[2])
        
        return operand1, operator, operand2
    except (ValueError, IndexError):
        return None


def calculate(operand1, operator, operand2):
    """
    Perform the calculation based on operator.
    
    Returns the result or None if operator is unknown.
    """
    if operator == "+":
        return add(operand1, operand2)
    elif operator == "-":
        return subtract(operand1, operand2)
    elif operator == "*":
        return multiply(operand1, operand2)
    elif operator == "/":
        return divide(operand1, operand2)
    else:
        return None


def main():
    """Run the calculator in a loop until user exits."""
    print("\n" + "=" * 50)
    print("       SIMPLE TERMINAL CALCULATOR")
    print("=" * 50)
    print("\nSupported operators: +, -, *, /")
    print("Format: <number> <operator> <number>")
    print("Example: 5 + 3")
    print("Type 'exit' or 'quit' to stop.\n")
    
    while True:
        try:
            user_input = input("Enter calculation (or 'exit'/'quit'): ").strip()
            
            # Check for exit commands
            if user_input.lower() in ("exit", "quit"):
                print("\nThank you for using the calculator. Goodbye!\n")
                break
            
            # Skip empty input
            if not user_input:
                print("Invalid input. Please try again.\n")
                continue
            
            # Parse input
            parsed = parse_input(user_input)
            if parsed is None:
                print("Invalid format. Please use: <number> <operator> <number>\n")
                continue
            
            operand1, operator, operand2 = parsed
            
            # Check if operator is valid
            if operator not in ("+", "-", "*", "/"):
                print(f"Unknown operator '{operator}'. Valid operators: +, -, *, /\n")
                continue
            
            # Calculate result
            try:
                result = calculate(operand1, operator, operand2)
                print(f"Result: {operand1} {operator} {operand2} = {result}\n")
            except ValueError as e:
                print(f"Error: {e}\n")
        
        except KeyboardInterrupt:
            print("\n\nCalculator interrupted. Goodbye!\n")
            break
        except Exception as e:
            print(f"Unexpected error: {e}. Please try again.\n")


if __name__ == "__main__":
    main()
