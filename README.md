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
