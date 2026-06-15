# deslackify

A tool to remove your own slack messages.

`deslackify` can only delete messages that *you* sent. The token you provide
authenticates as your own account, so it cannot remove messages authored by
other users.

`deslackify` supports Python 3.10 through 3.14.

## Installation

Install the `deslackify` command with [uv](https://docs.astral.sh/uv/):

```sh
uv tool install deslackify
```

## Obtaining credentials

`deslackify` is meant to be run without the overhead of creating a Slack app. It
authenticates as your own browser session, using two values copied from your
logged-in Slack web client (`https://app.slack.com`):

1. Open your workspace in a browser and open the developer tools.
2. **Token** — in the __Console__, run:
   ```js
   (d=>d.teams[Object.keys(d.teams)[0]].token)(JSON.parse(localStorage.localConfig_v2))
   ```
   It begins with `xoxc-`. This is the `TOKEN` below.
3. **Cookie** — in __Application → Cookies → `https://app.slack.com`__, copy the
   value of the `d` cookie. It begins with `xoxd-`. This is the `COOKIE` below.
   (`deslackify` re-encodes it as needed, so it does not matter whether the value
   is shown URL-encoded or not.)

The token and cookie must come from the same logged-in session.

### Alternative: a Slack app token

If you are able to create a Slack app, you can authenticate with a user OAuth
token instead of a browser session. It is more stable — it does not expire when
you sign out — and needs no `--cookie`:

1. Create a new app at https://api.slack.com/apps ("From scratch").
2. Under __OAuth & Permissions__, add the __User Token Scopes__ `search:read` and
   `chat:write`.
3. Click __Install to Workspace__ and authorize the app.
4. Copy the __User OAuth Token__ (it begins with `xoxp-`); use it as `TOKEN` and
   omit `--cookie`.

## Running

```sh
deslackify --token TOKEN --cookie COOKIE USERNAME
```

Both values can also be supplied via the `SLACK_TOKEN` and `SLACK_COOKIE`
environment variables (preferred, so the secrets do not appear in your shell
history or process list):

```sh
SLACK_TOKEN=… SLACK_COOKIE=… deslackify USERNAME
```

Or run it once without installing:

```sh
uvx deslackify --token TOKEN --cookie COOKIE USERNAME
```

Use `--dry-run` first to preview what would be deleted without deleting
anything.

By default `deslackify` will remove USERNAME's messages that are more than a
year old. You may also manually specify a `before` date via:

```sh
deslackify --token TOKEN --cookie COOKIE --before YYYY-MM-DD USERNAME
```

__Note__: If no results are found, you may need to replace `USERNAME` with
`USERID`. You can find the `USERID` by going to `Profile & Account`, and then
clicking the three dots, and at the bottom, "Copy member ID".
