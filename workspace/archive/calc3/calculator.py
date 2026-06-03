import tkinter as tk
from tkinter import font


class Calculator:
    """A simple GUI calculator application using tkinter."""
    
    def __init__(self, root):
        """Initialize the calculator GUI.
        
        Args:
            root: The tkinter root window.
        """
        self.root = root
        self.root.title("Simple Calculator")
        self.root.geometry("400x500")
        self.root.resizable(False, False)
        
        # Variable to store the current expression
        self.expression = ""
        
        # Create the display and buttons
        self.create_widgets()
    
    def create_widgets(self):
        """Create and layout all GUI widgets."""
        # Define fonts
        display_font = font.Font(family="Helvetica", size=24, weight="bold")
        button_font = font.Font(family="Helvetica", size=18)
        
        # Create a frame for the display
        display_frame = tk.Frame(self.root, bg="lightgray", height=100)
        display_frame.pack(fill=tk.BOTH, padx=10, pady=10)
        display_frame.pack_propagate(False)
        
        # Create the display/entry field
        self.display = tk.Entry(
            display_frame,
            font=display_font,
            borderwidth=2,
            relief=tk.SUNKEN,
            justify=tk.RIGHT,
            state=tk.DISABLED
        )
        self.display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create a frame for buttons
        button_frame = tk.Frame(self.root)
        button_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Define button layout: [['7', '8', '9', '/'], ['4', '5', '6', '*'], ...]
        buttons = [
            ['7', '8', '9', '/'],
            ['4', '5', '6', '*'],
            ['1', '2', '3', '-'],
            ['0', '.', '=', '+'],
            ['C']
        ]
        
        # Create buttons using grid layout
        for row_idx, row in enumerate(buttons):
            for col_idx, button_text in enumerate(row):
                self.create_button(
                    button_frame,
                    button_text,
                    row_idx,
                    col_idx,
                    button_font
                )
    
    def create_button(self, parent, text, row, col, font_obj):
        """Create and place a button in the grid.
        
        Args:
            parent: The parent frame.
            text: The button label.
            row: The grid row index.
            col: The grid column index.
            font_obj: The font for the button text.
        """
        # Determine button color and command based on text
        if text == 'C':
            bg_color = "red"
            fg_color = "white"
            command = self.clear
        elif text == '=':
            bg_color = "green"
            fg_color = "white"
            command = self.calculate
        elif text in ['+', '-', '*', '/']:
            bg_color = "orange"
            fg_color = "white"
            command = lambda: self.append_to_expression(text)
        elif text == '.':
            bg_color = "lightblue"
            command = lambda: self.append_to_expression(text)
        else:
            bg_color = "lightgray"
            command = lambda: self.append_to_expression(text)
        
        button = tk.Button(
            parent,
            text=text,
            font=font_obj,
            bg=bg_color,
            fg=fg_color if text in ['C', '='] or text in ['+', '-', '*', '/'] else "black",
            activebackground="darkgray",
            command=command
        )
        
        # Grid placement: clear button spans 4 columns
        if text == 'C':
            button.grid(row=row, column=0, columnspan=4, sticky="nsew", padx=5, pady=5)
        else:
            button.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
        
        # Configure grid weights for resizing
        parent.grid_rowconfigure(row, weight=1)
        parent.grid_columnconfigure(col, weight=1)
    
    def append_to_expression(self, value):
        """Append a character to the current expression.
        
        Args:
            value: The character to append (digit, operator, or decimal point).
        """
        self.expression += str(value)
        self.update_display()
    
    def update_display(self):
        """Update the display to show the current expression."""
        self.display.config(state=tk.NORMAL)
        self.display.delete(0, tk.END)
        self.display.insert(0, self.expression)
        self.display.config(state=tk.DISABLED)
    
    def calculate(self):
        """Evaluate the expression and display the result."""
        try:
            # Evaluate the expression
            result = eval(self.expression)
            self.expression = str(result)
            self.update_display()
        except ZeroDivisionError:
            # Handle division by zero
            self.expression = ""
            self.display.config(state=tk.NORMAL)
            self.display.delete(0, tk.END)
            self.display.insert(0, "Error")
            self.display.config(state=tk.DISABLED)
        except (SyntaxError, NameError, TypeError):
            # Handle invalid expressions
            self.expression = ""
            self.display.config(state=tk.NORMAL)
            self.display.delete(0, tk.END)
            self.display.insert(0, "Error")
            self.display.config(state=tk.DISABLED)
    
    def clear(self):
        """Clear the expression and reset the display."""
        self.expression = ""
        self.update_display()


if __name__ == "__main__":
    root = tk.Tk()
    calculator = Calculator(root)
    root.mainloop()
