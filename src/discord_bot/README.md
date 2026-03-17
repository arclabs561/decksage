# DeckSage Discord Bot

Thin Discord client over the DeckSage REST API. Provides slash commands for card similarity search, text search, deck parsing, and deck completion.

## Prerequisites

- Python 3.11+
- A running DeckSage API instance (default: `http://localhost:8001`)
- A Discord bot token

## Creating the Discord Application

1. Go to https://discord.com/developers/applications and create a new application.
2. Under **Bot**, click **Reset Token** and copy the token.
3. Under **OAuth2 > URL Generator**, select scopes: `bot`, `applications.commands`.
4. Select bot permissions: `Send Messages`, `Embed Links`, `Use Slash Commands`.
5. Copy the generated URL and open it in a browser to invite the bot to your server.

## Running

```bash
export DISCORD_TOKEN="your-bot-token"
export DECKSAGE_API_URL="http://localhost:8001"  # optional, this is the default

uv run src/discord_bot/bot.py
```

Or install the optional dependency group and run as a module:

```bash
uv pip install -e ".[discord]"
DISCORD_TOKEN="your-bot-token" python src/discord_bot/bot.py
```

## Slash Commands

| Command | Description |
|---------|-------------|
| `/similar <card_name> [game] [mode] [k]` | Find similar cards. Modes: synergy, substitute, meta, embedding, jaccard, fusion. |
| `/search <query> [game] [limit]` | Search for cards by text query. |
| `/parse <deck_text> [game]` | Parse a deck list and display the structured breakdown. |
| `/complete <deck_text> [game] [target_size]` | Parse and complete a partial deck list. |

All commands default to `game=magic`. Supported games: magic, pokemon, yugioh.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_TOKEN` | Yes | -- | Discord bot token |
| `DECKSAGE_API_URL` | No | `http://localhost:8001` | Base URL for the DeckSage API |

## Embed Colors

Responses use game-specific embed colors: purple (Magic), red (Pokemon), gold (Yu-Gi-Oh).
