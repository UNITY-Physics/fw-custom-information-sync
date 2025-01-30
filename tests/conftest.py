import pytest

pytest_plugins = ("flywheel_gear_toolkit.testing",)


@pytest.fixture
def print_captured():
    def _method(captured):
        """Show what has been captured in std out and err."""

        print("\nout")
        for ii, msg in enumerate(captured.out.split("\n")):
            print(f"{ii:2d} {msg}")
        print("\nerr")
        for ii, msg in enumerate(captured.err.split("\n")):
            print(f"{ii:2d} {msg}")

    return _method


@pytest.fixture
def search_stdout_contains():
    def _method(captured, find_me, contains_me):
        """Search stdout message for find_me, return true if it contains contains_me"""

        for msg in captured.out.split("/n"):
            if find_me in msg:
                if contains_me in msg:
                    return True
        return False

    return _method


@pytest.fixture
def search_sysout():
    def _method(captured, find_me):
        """Search capsys message for find_me, return message"""

        for msg in captured.out.split("/n"):
            if find_me in msg:
                return msg
        return ""

    return _method


@pytest.fixture
def search_syserr():
    def _method(captured, find_me):
        """Search capsys message for find_me, return message"""

        for msg in captured.err.split("\n"):
            if find_me in msg:
                return msg
        return ""

    return _method


@pytest.fixture
def print_caplog():
    def _method(caplog):
        """Show what has been captured in the log."""

        print("\nmessages")
        for ii, msg in enumerate(caplog.messages):
            print(f"{ii:2d} {msg}")
        print("\nrecords")
        for ii, rec in enumerate(caplog.records):
            print(f"{ii:2d} {rec}")

    return _method


@pytest.fixture
def search_caplog():
    def _method(caplog, find_me):
        """Search caplog message for find_me, return message"""

        for msg in caplog.messages:
            if find_me in msg:
                return msg
        return ""

    return _method


@pytest.fixture
def search_caplog_contains():
    def _method(caplog, find_me, contains_me):
        """Search caplog message for find_me, return true if it contains contains_me"""

        for msg in caplog.messages:
            if find_me in msg:
                if contains_me in msg:
                    return True
        return False

    return _method
