"""
Interactive CLI for the Calculator application.
"""

from calculator import Calculator


def display_menu():
    """Display the main menu options."""
    print("\n" + "=" * 50)
    print("            SIMPLE CALCULATOR")
    print("=" * 50)
    print("1. Add (+)")
    print("2. Subtract (-)")
    print("3. Multiply (*)")
    print("4. Divide (/)")
    print("5. View History")
    print("6. Clear History")
    print("7. Quit")
    print("-" * 50)


def get_operation_choice():
    """
    Get and validate the user's operation choice.
    
    Returns:
        str: A valid operation choice ('1'-'7').
    """
    while True:
        choice = input("Enter your choice (1-7): ").strip()
        if choice in ["1", "2", "3", "4", "5", "6", "7"]:
            return choice
        print("Invalid choice. Please enter a number between 1 and 7.")


def get_number(prompt="Enter a number: "):
    """
    Get and validate a numeric input from the user.
    
    Args:
        prompt (str): The prompt to display to the user.
        
    Returns:
        float: The validated number.
    """
    while True:
        try:
            value = float(input(prompt))
            return value
        except ValueError:
            print("Invalid input. Please enter a valid number.")


def perform_calculation(calc, operation, a, b):
    """
    Perform a calculation and handle errors gracefully.
    
    Args:
        calc (Calculator): The calculator instance.
        operation (int): The operation code (1-4).
        a (float): The first operand.
        b (float): The second operand.
        
    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        if operation == 1:
            result = calc.add(a, b)
            op_symbol = "+"
        elif operation == 2:
            result = calc.subtract(a, b)
            op_symbol = "-"
        elif operation == 3:
            result = calc.multiply(a, b)
            op_symbol = "*"
        elif operation == 4:
            result = calc.divide(a, b)
            op_symbol = "/"
        
        print(f"\n{a} {op_symbol} {b} = {result}")
        return True
    except ValueError as e:
        print(f"\nError: {e}")
        return False


def main():
    """Main CLI loop for the calculator."""
    calc = Calculator()
    
    print("\nWelcome to the Simple Calculator!")
    print("This calculator tracks all your operations in history.")
    
    while True:
        display_menu()
        choice = get_operation_choice()
        
        if choice == "7":
            print("\nThank you for using the Simple Calculator. Goodbye!")
            break
        
        elif choice == "5":
            print("\n" + calc.show_history())
        
        elif choice == "6":
            calc.clear_history()
            print("\nHistory cleared.")
        
        elif choice in ["1", "2", "3", "4"]:
            # Get operands
            num1 = get_number("\nEnter first number: ")
            num2 = get_number("Enter second number: ")
            
            # Perform calculation
            perform_calculation(calc, int(choice), num1, num2)


if __name__ == "__main__":
    main()
