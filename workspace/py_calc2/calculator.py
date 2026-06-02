#!/usr/bin/env python3
"""
Simple Terminal Calculator
A basic calculator that runs in a loop and supports four basic operations.
"""


def display_welcome():
    """Display a friendly welcome message and usage instructions."""
    print("=" * 50)
    print("Welcome to the Simple Terminal Calculator!")
    print("=" * 50)
    print("\nUsage:")
    print("  Enter calculations in the format: number operator number")
    print("  Examples: 3 + 5, 10 - 2, 4 * 7, 15 / 3")
    print("\nSupported operators:")
    print("  + (addition)")
    print("  - (subtraction)")
    print("  * (multiplication)")
    print("  / (division)")
    print("\nType 'quit' or 'exit' to close the calculator.")
    print("=" * 50 + "\n")


def parse_input(user_input):
    """
    Parse user input and return (operand1, operator, operand2).
    
    Args:
        user_input (str): The input string from the user
        
    Returns:
        tuple: (operand1, operator, operand2) or (None, None, None) if invalid
    """
    tokens = user_input.strip().split()
    
    # Check if we have exactly 3 tokens
    if len(tokens) != 3:
        return None, None, None
    
    try:
        operand1 = float(tokens[0])
        operator = tokens[1]
        operand2 = float(tokens[2])
        return operand1, operator, operand2
    except ValueError:
        return None, None, None


def calculate(operand1, operator, operand2):
    """
    Perform the calculation based on the operator.
    
    Args:
        operand1 (float): The first number
        operator (str): The operator (+, -, *, /)
        operand2 (float): The second number
        
    Returns:
        tuple: (result, error_message) where error_message is None if successful
    """
    if operator == '+':
        return operand1 + operand2, None
    elif operator == '-':
        return operand1 - operand2, None
    elif operator == '*':
        return operand1 * operand2, None
    elif operator == '/':
        if operand2 == 0:
            return None, "Error: Cannot divide by zero!"
        return operand1 / operand2, None
    else:
        return None, "Error: Unknown operator. Use +, -, *, or /"


def main():
    """Main calculator loop."""
    display_welcome()
    
    while True:
        try:
            user_input = input("Enter calculation (or 'quit'/'exit' to exit): ").strip()
            
            # Check for exit commands
            if user_input.lower() in ('quit', 'exit'):
                print("\nThank you for using the calculator. Goodbye!")
                break
            
            # Handle empty input
            if not user_input:
                print("Error: Please enter a valid calculation.\n")
                continue
            
            # Parse the input
            operand1, operator, operand2 = parse_input(user_input)
            
            if operand1 is None or operator is None or operand2 is None:
                print("Error: Invalid format. Use: number operator number\n")
                continue
            
            # Perform the calculation
            result, error = calculate(operand1, operator, operand2)
            
            if error:
                print(f"{error}\n")
            else:
                print(f"Result: {operand1} {operator} {operand2} = {result}\n")
                
        except KeyboardInterrupt:
            print("\n\nCalculator interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"Unexpected error: {e}\n")


if __name__ == "__main__":
    main()
