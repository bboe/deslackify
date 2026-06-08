# deslackify

A tool to remove your own slack messages.

`deslackify` can only delete messages that *you* sent. The token you provide
authenticates as your own account, so it cannot remove messages authored by
other users.

## Installation

```sh
pip install deslackify
```

## Obtaining a Slack Token

__Note__: Slack [discontinued legacy
tokens](https://api.slack.com/legacy/custom-integrations/legacy-tokens) in 2020,
so they can no longer be generated. Use a Slack app user token instead:

1. Create a new app at https://api.slack.com/apps ("From scratch").
2. Under __OAuth & Permissions__, add the following __User Token Scopes__:
   `search:read` and `chat:write`.
3. Click __Install to Workspace__ and authorize the app.
4. Copy the __User OAuth Token__ (it begins with `xoxp-`); use it as `TOKEN`
   below.

## Running

```sh
deslackify --token TOKEN USERNAME
```

By default `deslackify` will remove USERNAME's messages that are more than a
year old. You may also manually specify a `before` date via:

```sh
deslackify --token TOKEN --before YYYY-MM-DD USERNAME
```

__Note__: If no results are found, you may need to replace `USERNAME` with
`USERID`. You can find the `USERID` by going to `Profile & Account`, and then
clicking the three dots, and at the bottom, "Copy member ID".