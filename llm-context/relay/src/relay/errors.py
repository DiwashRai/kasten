"""Relay's errors and the exit code each one maps to."""

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_ANSWER = 3
EXIT_NO_DAEMON = 4


class RelayError(Exception):
    """Something went wrong; the message says what. Maps to EXIT_USAGE."""


class NoAnswerYet(RelayError):
    """A wait ended before the user answered. Callers end the turn and try again later."""


class DaemonUnreachable(RelayError):
    """The daemon could not be started or reached. Status verbs carry on without it."""
