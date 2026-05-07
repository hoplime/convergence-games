class UserNotLoggedInError(Exception):
    """Exception raised when a user must be logged in to perform an action."""

    pass


class SlugRedirectError(Exception):
    """Raised by route dependencies to 301 a sqid-form URL to its canonical slug-form URL."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path
