# Simple Terminal Calculator

A lightweight, easy-to-use calculator that runs in your terminal.

## Features

- **Basic arithmetic operations**: addition (+), subtraction (-), multiplication (*), division (/)
- **Error handling**: gracefully handles division by zero and invalid input
- **Continuous operation**: runs in a loop until you exit
- **Clean interface**: clear prompts and formatted output

## Installation

No external dependencies required. Python 3.x is needed.

## Usage

Run the calculator:

```bash
python3 calculator.py
```

### Input Format

Enter calculations in the format: `<number> <operator> <number>`

### Examples

```
Enter calculation (or 'exit'/'quit'): 5 + 3
Result: 5.0 + 3 = 8.0

Enter calculation (or 'exit'/'quit'): 10 / 2
Result: 10.0 / 2 = 5.0

Enter calculation (or 'exit'/'quit'): 7 * 6
Result: 7.0 * 6 = 42.0
```

### Exit

To stop the calculator, type `exit` or `quit`:

```
Enter calculation (or 'exit'/'quit'): exit
Thank you for using the calculator. Goodbye!
```

## Error Handling

- **Division by zero**: Displays an error message and prompts for new input
- **Invalid format**: Shows usage instructions if input doesn't match expected format
- **Non-numeric values**: Gracefully rejects non-numeric input
- **Unknown operators**: Informs user of valid operators

## Examples

### Valid inputs:
- `5 + 3`
- `10.5 - 2.3`
- `4 * 7`
- `100 / 4`

### Invalid inputs (will show error):
- `5 3` (missing operator)
- `5 ^ 3` (unknown operator)
- `abc + def` (non-numeric)
- `10 / 0` (division by zero)
