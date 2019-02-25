# deslackify

A tool to remove your own slack messages.

## Installation

```sh
pip install deslackify
```

## Obtaining Slack Legacy Token

Generate a token via: https://api.slack.com/custom-integrations/legacy-tokens

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