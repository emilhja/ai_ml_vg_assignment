#!/usr/bin/env python3
"""
Simple terminal-based number guessing game.
"""

import random


def get_valid_input(prompt):
    """Get a valid integer input from the user."""
    while True:
        try:
            user_input = input(prompt)
            return int(user_input)
        except ValueError:
            print("Invalid input! Please enter a valid integer.")


def play_game():
    """Play a single round of the guessing game."""
    secret_number = random.randint(1, 100)
    attempts = 0
    max_attempts = 10

    print("\n" + "=" * 50)
    print("Welcome to the Number Guessing Game!")
    print(f"I'm thinking of a number between 1 and 100.")
    print(f"You have {max_attempts} attempts to guess it.")
    print("=" * 50 + "\n")

    while attempts < max_attempts:
        attempts += 1
        remaining = max_attempts - attempts + 1

        guess = get_valid_input(
            f"Attempt {attempts}/{max_attempts} - Enter your guess: "
        )

        if guess == secret_number:
            print(f"\n🎉 You win! You guessed the number {secret_number}!")
            print(f"You got it in {attempts} attempt(s)!")
            return True

        elif guess < secret_number:
            print(f"❌ Too low! Try again. ({remaining} attempts left)")

        else:
            print(f"❌ Too high! Try again. ({remaining} attempts left)")

    print(f"\n😢 You lose! The number was {secret_number}.")
    print(f"You used all {max_attempts} attempts.")
    return False


def main():
    """Main game loop with replay option."""
    play_again = True

    while play_again:
        play_game()

        while True:
            response = input("\nDo you want to play again? (yes/no): ").strip().lower()
            if response in ("yes", "y"):
                play_again = True
                break
            elif response in ("no", "n"):
                play_again = False
                break
            else:
                print("Please enter 'yes' or 'no'.")

    print("\nThanks for playing! Goodbye!")


if __name__ == "__main__":
    main()
