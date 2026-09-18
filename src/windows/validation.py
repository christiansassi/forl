"""Shared argument validation helpers.

Every public function in this project validates its arguments through the
helpers defined here so that type and range checks are written once and raise
consistent, named errors.
"""

from __future__ import annotations

from typing import Any


def require_type(value: Any, expected: type | tuple[type, ...], name: str) -> None:
	"""Raise TypeError unless a value is an instance of the expected type.

	Args:
		value: The argument value to check. Any type.
		expected: The type, or tuple of types, the value must be an instance of.
		name: Name of the argument, used in the error message. str.

	Returns:
		None. Raises TypeError when the check fails.
	"""
	if not isinstance(value, expected):
		names = expected.__name__ if isinstance(expected, type) else " or ".join(t.__name__ for t in expected)
		raise TypeError(f"{name} must be {names}, got {type(value).__name__}")


def require_non_empty_str(value: Any, name: str) -> str:
	"""Return a string argument after checking that it is a non-empty string.

	Args:
		value: The argument value to check. Any type.
		name: Name of the argument, used in the error message. str.

	Returns:
		str: The validated value, unchanged.
	"""
	require_type(value, str, name)
	if not value.strip():
		raise ValueError(f"{name} must be a non-empty string")
	return value


def require_number_in_range(value: Any, low: float, high: float, name: str) -> float:
	"""Return a numeric argument after checking that it lies within an inclusive range.

	Booleans are rejected because ``bool`` is a subclass of ``int`` and a boolean
	is never a meaningful measurement here.

	Args:
		value: The argument value to check. Expected int or float.
		low: Smallest accepted value, inclusive. float.
		high: Largest accepted value, inclusive. float.
		name: Name of the argument, used in the error message. str.

	Returns:
		float: The validated value, converted to float.
	"""
	if isinstance(value, bool):
		raise TypeError(f"{name} must be int or float, got bool")
	require_type(value, (int, float), name)
	if not low <= value <= high:
		raise ValueError(f"{name} must be between {low} and {high}, got {value}")
	return float(value)


def require_positive_int(value: Any, name: str) -> int:
	"""Return an integer argument after checking that it is strictly positive.

	Args:
		value: The argument value to check. Expected int.
		name: Name of the argument, used in the error message. str.

	Returns:
		int: The validated value, unchanged.
	"""
	if isinstance(value, bool):
		raise TypeError(f"{name} must be int, got bool")
	require_type(value, int, name)
	if value <= 0:
		raise ValueError(f"{name} must be greater than 0, got {value}")
	return value


def require_member(value: Any, allowed: frozenset[str], name: str) -> str:
	"""Return a string argument after checking that it belongs to an allowed set.

	Args:
		value: The argument value to check. Expected str.
		name: Name of the argument, used in the error message. str.
		allowed: The set of accepted values. frozenset[str].

	Returns:
		str: The validated value, unchanged.
	"""
	require_type(value, str, name)
	if value not in allowed:
		raise ValueError(f"{name} must be one of {sorted(allowed)}, got {value!r}")
	return value
