import argparse

import pytest
import slacker
from requests import HTTPError

import deslackify
from deslackify import cli


class FakeHTTPResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class FakeResponse:
    def __init__(self, body=None, *, successful=True):
        self.body = {"ok": True} if body is None else body
        self.successful = successful


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)


def http_error(status_code, *, retry_after="0"):
    return HTTPError(response=FakeHTTPResponse(status_code, {"retry-after": retry_after}))


def test_delete_message_delete_only():
    calls = []

    class FakeChat:
        def delete(self, **kwargs):
            calls.append("delete")
            return FakeResponse()

    class FakeSlack:
        chat = FakeChat()

    cli.delete_message(FakeSlack(), {"channel": {"id": "C1"}, "ts": "1"})
    assert calls == ["delete"]


def test_delete_message_updates_then_deletes():
    calls = []

    class FakeChat:
        def update(self, **kwargs):
            calls.append(("update", kwargs))
            return FakeResponse()

        def delete(self, **kwargs):
            calls.append(("delete", kwargs))
            return FakeResponse()

    class FakeSlack:
        chat = FakeChat()

    message = {"channel": {"id": "C1"}, "ts": "123"}
    cli.delete_message(FakeSlack(), message, update_first=True)
    assert [name for name, _ in calls] == ["update", "delete"]
    assert calls[0][1] == {"as_user": True, "channel": "C1", "text": "-", "ts": "123"}


def test_handle_rate_limit_gives_up():
    def method():
        raise http_error(429)

    with pytest.raises(cli.RetryError):
        cli.handle_rate_limit(method)


def test_handle_rate_limit_reraises_other_http_errors():
    def method():
        raise http_error(500)

    with pytest.raises(HTTPError):
        cli.handle_rate_limit(method)


def test_handle_rate_limit_retries_then_succeeds():
    outcomes = [http_error(429), FakeResponse()]

    def method():
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    assert cli.handle_rate_limit(method).body["ok"] is True
    assert outcomes == []


def test_handle_rate_limit_success():
    response = FakeResponse()
    assert cli.handle_rate_limit(lambda: response) is response


def test_handle_rate_limit_unsuccessful_raises():
    with pytest.raises(RuntimeError):
        cli.handle_rate_limit(lambda: FakeResponse(successful=False))


def test_normalize_d_cookie_encodes_decoded_value():
    assert cli._normalize_d_cookie("xoxd-a/b+c") == "xoxd-a%2Fb%2Bc"


def test_normalize_d_cookie_extracts_d_from_full_header():
    header = "b=hex; d=xoxd-a/b+c; d-s=123"
    assert cli._normalize_d_cookie(header) == "xoxd-a%2Fb%2Bc"


def test_normalize_d_cookie_is_idempotent_on_encoded_value():
    assert cli._normalize_d_cookie("xoxd-a%2Fb%2Bc") == "xoxd-a%2Fb%2Bc"


def test_run_counts_slacker_errors(monkeypatch):
    message = {"channel": {"id": "C1"}, "text": "hello", "ts": "1609459200.000"}
    monkeypatch.setattr(cli, "search_messages", lambda *_a, **_k: iter([message]))

    def raise_error(*_args, **_kwargs):
        raise slacker.Error("cant_delete_message")

    monkeypatch.setattr(cli, "delete_message", raise_error)
    args = argparse.Namespace(
        after=None,
        before="2021-01-01",
        dry_run=False,
        update=False,
        user="alice",
    )
    assert cli.run(object(), args) == 0


def test_run_dry_run_does_not_delete(monkeypatch):
    message = {"channel": {"id": "C1"}, "text": "hello", "ts": "1609459200.000"}
    monkeypatch.setattr(cli, "search_messages", lambda *_a, **_k: iter([message]))
    deleted = []
    monkeypatch.setattr(cli, "delete_message", lambda *a, **k: deleted.append(True))
    args = argparse.Namespace(
        after=None,
        before="2021-01-01",
        dry_run=True,
        update=False,
        user="alice",
    )
    assert cli.run(object(), args) == 0
    assert deleted == []


def test_search_messages_builds_query_and_paginates():
    captured = []

    class FakeSearch:
        def messages(self, **kwargs):
            captured.append(kwargs)
            return FakeResponse({
                "messages": {
                    "matches": [{"ts": "2"}, {"ts": "1"}],
                    "paging": {"pages": 2},
                    "total": 3,
                },
                "ok": True,
            })

    class FakeSlack:
        search = FakeSearch()

    results = list(
        cli.search_messages(FakeSlack(), "alice", after="2020-01-01", before="2021-01-01"),
    )
    assert captured[0]["query"] == "from:alice after:2020-01-01 before:2021-01-01"
    assert [match["ts"] for match in results] == ["1", "2", "1", "2"]


def test_search_messages_without_after():
    class FakeSearch:
        def messages(self, **kwargs):
            self.query = kwargs["query"]
            return FakeResponse({
                "messages": {"matches": [], "paging": {"pages": 0}, "total": 0},
                "ok": True,
            })

    search = FakeSearch()

    class FakeSlack:
        pass

    slack = FakeSlack()
    slack.search = search
    assert list(cli.search_messages(slack, "bob", after=None, before="x")) == []
    assert search.query == "from:bob before:x"


def test_session_sets_encoded_d_cookie():
    session = cli._session("xoxd-a/b+c")
    assert session.cookies.get("d") == "xoxd-a%2Fb%2Bc"


def test_session_without_cookie_sets_nothing():
    assert cli._session(None).cookies.get("d") is None


def test_version():
    assert deslackify.__version__
