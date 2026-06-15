import argparse

import pytest
from requests import HTTPError

import deslackify
from deslackify import cli


class FakeClient:
    def __init__(self, responses=None):
        self.calls = []
        self._responses = responses or {}

    def call(self, method, **params):
        self.calls.append((method, params))
        result = self._responses.get(method)
        if isinstance(result, Exception):
            raise result
        return result if result is not None else {"ok": True}


class FakeHTTPResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class FakePostResponse:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, body):
        self._body = body
        self.posted = []

    def post(self, url, **kwargs):
        self.posted.append((url, kwargs))
        return FakePostResponse(self._body)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)


def http_error(status_code, *, retry_after="0"):
    return HTTPError(response=FakeHTTPResponse(status_code, {"retry-after": retry_after}))


def test_client_call_posts_bearer_token_and_returns_body():
    client = cli.SlackClient("xoxc-tok", None)
    client._session = FakeSession({"ok": True, "value": 1})
    assert client.call("search.messages", query="q") == {"ok": True, "value": 1}
    url, kwargs = client._session.posted[0]
    assert url == "https://slack.com/api/search.messages"
    assert kwargs["headers"]["Authorization"] == "Bearer xoxc-tok"
    assert kwargs["data"] == {"query": "q"}


def test_client_call_raises_slack_error_when_not_ok():
    client = cli.SlackClient("tok", None)
    client._session = FakeSession({"error": "cant_delete_message", "ok": False})
    with pytest.raises(cli.SlackError, match="cant_delete_message"):
        client.call("chat.delete", ts="1")


def test_delete_message_delete_only():
    client = FakeClient()
    cli.delete_message(client, {"channel": {"id": "C1"}, "ts": "1"})
    assert [method for method, _ in client.calls] == ["chat.delete"]


def test_delete_message_updates_then_deletes():
    client = FakeClient()
    cli.delete_message(client, {"channel": {"id": "C1"}, "ts": "123"}, update_first=True)
    assert [method for method, _ in client.calls] == ["chat.update", "chat.delete"]
    assert client.calls[0][1] == {
        "as_user": "true",
        "channel": "C1",
        "text": "-",
        "ts": "123",
    }


def test_handle_rate_limit_gives_up():
    def call():
        raise http_error(429)

    with pytest.raises(cli.RetryError):
        cli.handle_rate_limit(call)


def test_handle_rate_limit_reraises_other_http_errors():
    def call():
        raise http_error(500)

    with pytest.raises(HTTPError):
        cli.handle_rate_limit(call)


def test_handle_rate_limit_retries_then_succeeds():
    outcomes = [http_error(429), {"ok": True}]

    def call():
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    assert cli.handle_rate_limit(call) == {"ok": True}
    assert outcomes == []


def test_handle_rate_limit_success():
    body = {"ok": True}
    assert cli.handle_rate_limit(lambda: body) is body


@pytest.mark.parametrize("value", ["2026-06-15", "2020-01-01", "1999-12-31"])
def test_is_valid_date_accepts_iso_dates(value):
    assert cli._is_valid_date(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "2026-6-15",  # not zero-padded
        "06/14/2026",  # slash format
        "20260615",  # no separators
        "2026-06-15T00:00:00",  # includes a time
        "yesterday",  # relative word
        "1 hour ago",  # relative phrase
        "2026-13-01",  # invalid month
        "2026-06-32",  # invalid day
        "",  # empty
    ],
)
def test_is_valid_date_rejects_non_iso_values(value):
    assert cli._is_valid_date(value) is False


def test_normalize_d_cookie_encodes_decoded_value():
    assert cli._normalize_d_cookie("xoxd-a/b+c") == "xoxd-a%2Fb%2Bc"


def test_normalize_d_cookie_extracts_d_from_full_header():
    header = "b=hex; d=xoxd-a/b+c; d-s=123"
    assert cli._normalize_d_cookie(header) == "xoxd-a%2Fb%2Bc"


def test_normalize_d_cookie_is_idempotent_on_encoded_value():
    assert cli._normalize_d_cookie("xoxd-a%2Fb%2Bc") == "xoxd-a%2Fb%2Bc"


def test_run_counts_slack_errors(monkeypatch):
    message = {"channel": {"id": "C1"}, "text": "hello", "ts": "1609459200.000"}
    monkeypatch.setattr(cli, "search_messages", lambda *_a, **_k: iter([message]))

    def raise_error(*_args, **_kwargs):
        raise cli.SlackError("cant_delete_message")

    monkeypatch.setattr(cli, "delete_message", raise_error)
    args = argparse.Namespace(
        after=None, before="2021-01-01", dry_run=False, update=False, user="alice"
    )
    assert cli.run(object(), args) == 0


def test_run_dry_run_does_not_delete(monkeypatch):
    message = {"channel": {"id": "C1"}, "text": "hello", "ts": "1609459200.000"}
    monkeypatch.setattr(cli, "search_messages", lambda *_a, **_k: iter([message]))
    deleted = []
    monkeypatch.setattr(cli, "delete_message", lambda *a, **k: deleted.append(True))
    args = argparse.Namespace(
        after=None, before="2021-01-01", dry_run=True, update=False, user="alice"
    )
    assert cli.run(object(), args) == 0
    assert deleted == []


def test_search_messages_builds_query_and_paginates():
    body = {
        "messages": {
            "matches": [{"ts": "2"}, {"ts": "1"}],
            "paging": {"pages": 2},
            "total": 3,
        },
        "ok": True,
    }
    client = FakeClient({"search.messages": body})
    results = list(cli.search_messages(client, "alice", after="2020-01-01", before="2021-01-01"))
    assert client.calls[0][1]["query"] == "from:alice after:2020-01-01 before:2021-01-01"
    assert [match["ts"] for match in results] == ["1", "2", "1", "2"]


def test_search_messages_without_after():
    body = {"messages": {"matches": [], "paging": {"pages": 0}, "total": 0}, "ok": True}
    client = FakeClient({"search.messages": body})
    assert list(cli.search_messages(client, "bob", after=None, before="x")) == []
    assert client.calls[0][1]["query"] == "from:bob before:x"


def test_session_sets_encoded_d_cookie():
    session = cli._session("xoxd-a/b+c")
    assert session.cookies.get("d") == "xoxd-a%2Fb%2Bc"


def test_session_without_cookie_sets_nothing():
    assert cli._session(None).cookies.get("d") is None


def test_version():
    assert deslackify.__version__
