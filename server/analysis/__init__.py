"""Deterministic analysers for qvasp/VASP results.

Every function here reads files and returns plain data; nothing guesses a value it
could not parse. ``extract`` returns ``{"unsupported": reason}`` instead of inventing
numbers.
"""
