# Number Guessing Game

A simple terminal-based number guessing game written in Python.

## How to Run

```bash
python3 game.py
```

## How It Works

1. **Game Start**: The computer picks a random number between 1 and 100.
2. **Guessing**: You have 10 attempts to guess the number.
3. **Feedback**: After each guess, you'll receive feedback:
   - "Too low!" if your guess is less than the secret number
   - "Too high!" if your guess is greater than the secret number
   - "You win!" if you guess correctly
4. **Results**: 
   - Win: Display your score (number of attempts used)
   - Lose: Reveal the secret number after 10 failed attempts
5. **Replay**: After each round, choose whether to play again or exit

## Features

- ✅ Input validation (rejects non-integer inputs)
- ✅ Attempt counter and remaining attempts display
- ✅ Play multiple rounds without restarting
- ✅ Clear feedback after each guess
- ✅ Win/lose messages with statistics

## Requirements

- Python 3.x

## Example Session

```
==================================================
Welcome to the Number Guessing Game!
I'm thinking of a number between 1 and 100.
You have 10 attempts to guess it.
==================================================

Attempt 1/10 - Enter your guess: 50
❌ Too low! Try again. (9 attempts left)
Attempt 2/10 - Enter your guess: 75
❌ Too high! Try again. (8 attempts left)
Attempt 3/10 - Enter your guess: 62
🎉 You win! You guessed the number 62!
You got it in 3 attempt(s)!

Do you want to play again? (yes/no): no

Thanks for playing! Goodbye!
```
