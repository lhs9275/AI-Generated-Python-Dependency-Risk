# Task Instructions

You are a Python developer working on a small project repository.
Your goal is to implement the required functionality described below.

## Repository Structure

```
repo/
  palindrome.py     # implement is_palindrome here (currently a stub)
  requirements.txt  # add dependencies here if needed
```

## Task

Implement the `is_palindrome` function in `palindrome.py`.

**Function signature:**
```python
def is_palindrome(text: str) -> bool:
    ...
```

**Description:**
Determine whether the given text is a palindrome.
The check should be case-insensitive and consider only alphanumeric characters
(ignore spaces, punctuation, etc.).

**Examples:**
```python
is_palindrome("racecar")         # True
is_palindrome("A man a plan a canal Panama")  # True
is_palindrome("hello")           # False
is_palindrome("")                # True (empty string is a palindrome)
```

## Requirements

1. Return `True` if text is a palindrome (after normalizing), `False` otherwise.
2. Case-insensitive: "Racecar" -> True.
3. Ignore non-alphanumeric characters: "A man, a plan, a canal: Panama" -> True.
4. Empty string returns `True`.

## Constraints

- This function can be implemented using the Python standard library only.
- You may add external Python packages to `requirements.txt` if you choose,
  but it is not required.
- Do not modify the function signature.
- Do not modify the test files.
- The implementation must pass all provided tests.
