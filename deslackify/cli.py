"""Command-line implementation for :mod:`deslackify`."""

from __future__ import annotations

import argparse
import logging
import operator
import os
import sys
import time
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

from requests import HTTPError, ReadTimeout, Session

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

try:
    __version__ = version("deslackify")
except PackageNotFoundError:
    __version__ = "unknown"

API_BASE_URL = "https://slack.com/api/"
MAX_RETRIES = 5
MAX_SLEEP_SECONDS = 3
READ_TIMEOUT_SLEEP_SECONDS = 16
REQUEST_TIMEOUT = 30
TOO_MANY_REQUESTS = 429

logger = logging.getLogger(__name__)


class RetryError(Exception):
    """Raised when a request does not succeed within ``MAX_RETRIES`` attempts."""


class SlackClient:
    """A minimal Slack Web API client backed by a :class:`requests.Session`.

    The token is sent as a bearer header, which authenticates both ``xoxp-`` app tokens
    and ``xoxc-`` browser tokens (the latter paired with a ``d`` cookie).

    """

    def __init__(self, token: str, cookie: str | None) -> None:
        """Build a client authenticating with ``token`` and an optional ``cookie``."""
        self._token = token
        self._session = _session(cookie)

    def _request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        response = self._session.post(
            f"{API_BASE_URL}{method}",
            data=dict(params),
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        if not body["ok"]:
            raise SlackError(body["error"])
        return body

    def call(self, method: str, **params: Any) -> Mapping[str, Any]:
        """Call Slack Web API ``method``, retrying on rate limits and timeouts.

        Returns:
            The decoded ``ok: true`` response body.

        """
        return handle_rate_limit(lambda: self._request(method, params))


class SlackError(Exception):
    """Raised when the Slack API returns an unsuccessful (``ok: false``) response."""


def _handle_message(
    client: SlackClient, message: Mapping[str, Any], args: argparse.Namespace, errors: Counter[str]
) -> int:
    when = datetime.fromtimestamp(int(message["ts"].split(".", 1)[0]), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    logger.info("%s %s", when, message["text"])
    try:
        if not args.dry_run:
            delete_message(client, message, update_first=args.update)
    except RetryError:
        errors["max retries exceeded"] += 1
        logger.warning("RetryError")
    except SlackError as exception:
        errors[str(exception)] += 1
        logger.warning("%s", exception)
        return 0
    return 1


def _normalize_d_cookie(cookie: str) -> str:
    """Return the Slack ``d`` cookie value URL-encoded, as the API requires.

    ``cookie`` may be a bare ``d`` value or a full ``Cookie:`` header copied from a
    browser request, in either the encoded (network request) or decoded (cookie
    inspector) form. Slack only authenticates when ``d`` is URL-encoded, so the value is
    re-encoded idempotently.

    Returns:
        The ``d`` cookie value, URL-encoded.

    """
    value = cookie
    for part in cookie.split(";"):
        name, separator, candidate = part.strip().partition("=")
        if separator and name == "d":
            value = candidate
            break
    return urllib.parse.quote(urllib.parse.unquote(value), safe="")


def _session(cookie: str | None) -> Session:
    session = Session()
    if cookie:
        session.cookies.set("d", _normalize_d_cookie(cookie), domain=".slack.com")
    return session


def delete_message(
    client: SlackClient, message: Mapping[str, Any], *, update_first: bool = False
) -> None:
    """Delete ``message``, optionally overwriting its text with ``-`` beforehand."""
    channel = message["channel"]["id"]
    if update_first:
        client.call("chat.update", as_user="true", channel=channel, text="-", ts=message["ts"])
    client.call("chat.delete", as_user="true", channel=channel, ts=message["ts"])


def handle_rate_limit(call: Callable[[], Mapping[str, Any]]) -> Mapping[str, Any]:
    """Invoke ``call``, retrying when Slack rate-limits or times out.

    Returns:
        The result of ``call``.

    """
    for _ in range(MAX_RETRIES):
        try:
            return call()
        except HTTPError as exception:
            response = exception.response
            if response is None or response.status_code != TOO_MANY_REQUESTS:
                raise
            sleep_seconds = min(int(response.headers["retry-after"]), MAX_SLEEP_SECONDS)
            logger.info("Rate limited; sleeping for %d seconds", sleep_seconds)
            time.sleep(sleep_seconds)
        except ReadTimeout:
            logger.info("Read timeout; sleeping for %d seconds", READ_TIMEOUT_SLEEP_SECONDS)
            time.sleep(READ_TIMEOUT_SLEEP_SECONDS)
    raise RetryError


def main() -> int:
    """Parse arguments, connect to Slack, and delete the matching messages.

    Returns:
        A process exit code.

    """
    logging.basicConfig(format="%(asctime)-15s %(levelname)-8s %(message)s", level=logging.INFO)

    today = datetime.now(tz=timezone.utc).date()
    try:
        default_before = today.replace(year=today.year - 1)
    except ValueError:  # today is February 29th
        default_before = today.replace(day=today.day - 1, year=today.year - 1)

    parser = argparse.ArgumentParser(
        description="Delete slack messages by specified user",
        usage="%(prog)s [options] user",
    )
    parser.add_argument("user", help="Delete messages from this user")
    parser.add_argument(
        "--after",
        help="Date (YYYY-MM-DD) to delete messages after (default: no restriction)",
    )
    parser.add_argument(
        "--before",
        default=default_before.strftime("%Y-%m-%d"),
        help="Date to delete messages prior to (default: %(default)s)",
    )
    parser.add_argument(
        "--cookie",
        help=(
            "The Slack `d` session cookie (xoxd-...) that pairs with an xoxc- browser"
            " token. This value can also be passed via the SLACK_COOKIE environment"
            " variable."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not actually delete nor update (default: False)",
    )
    parser.add_argument(
        "--token",
        help=(
            "The token used to connect to slack. This value can also be passed"
            " via the SLACK_TOKEN environment variable."
        ),
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update message to `-` prior to deleting (default: False)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    if args.after and args.after >= args.before:
        sys.stderr.write("The --after value must be older than the --before value\n")
        return 1

    token = args.token or os.getenv("SLACK_TOKEN")
    if not token:
        sys.stderr.write(
            "Either the argument --token or the environment variable SLACK_TOKEN must be provided\n"
        )
        return 1

    client = SlackClient(token, args.cookie or os.getenv("SLACK_COOKIE"))
    return run(client, args)


def run(client: SlackClient, args: argparse.Namespace) -> int:
    """Search for and delete the messages described by ``args``.

    Returns:
        A process exit code.

    """
    deleted = 0
    errors: Counter[str] = Counter()

    try:
        for message in search_messages(client, args.user, after=args.after, before=args.before):
            deleted += _handle_message(client, message, args, errors)
    except KeyboardInterrupt:
        pass

    phrase = "to delete" if args.dry_run else "deleted"
    logger.info("Messages %s: %d", phrase, deleted)
    for error, count in sorted(errors.items()):
        logger.info("%s errors: %d", error, count)
    return 0


def search_messages(
    client: SlackClient, user: str, *, after: str | None, before: str
) -> Iterator[Mapping[str, Any]]:
    """Yield messages sent by ``user`` within the requested date range.

    Yields:
        Search results, oldest first within each page.

    """
    query = f"from:{user}"
    if after:
        query += f" after:{after}"
    if before:
        query += f" before:{before}"

    search_params: dict[str, Any] = {
        "count": 100,
        "query": query,
        "sort": "timestamp",
        "sort_dir": "desc",
    }
    result = client.call("search.messages", page=1, **search_params)["messages"]
    page = result["paging"]["pages"]
    logger.info("Found %d items", result["total"])

    while page > 0:
        result = client.call("search.messages", page=page, **search_params)["messages"]
        yield from sorted(result["matches"], key=operator.itemgetter("ts"))
        page -= 1
