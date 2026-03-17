# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "discord.py>=2.3.0",
#     "httpx>=0.27.0",
# ]
# ///
"""DeckSage Discord bot -- thin client over the DeckSage REST API.

Run with:  uv run src/discord_bot/bot.py
Env vars:  DISCORD_TOKEN (required), DECKSAGE_API_URL (default http://localhost:8001)
"""

from __future__ import annotations

import os
import sys
from typing import Any

import discord
import httpx
from discord import app_commands

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
API_URL = os.getenv("DECKSAGE_API_URL", "http://localhost:8001").rstrip("/")

GAME_COLORS: dict[str, discord.Color] = {
    "magic": discord.Color.purple(),
    "pokemon": discord.Color.red(),
    "yugioh": discord.Color.gold(),
}
GAME_CHOICES = [
    app_commands.Choice(name="Magic: The Gathering", value="magic"),
    app_commands.Choice(name="Pokemon TCG", value="pokemon"),
    app_commands.Choice(name="Yu-Gi-Oh!", value="yugioh"),
]
MODE_CHOICES = [
    app_commands.Choice(name="Synergy", value="synergy"),
    app_commands.Choice(name="Substitute", value="substitute"),
    app_commands.Choice(name="Meta", value="meta"),
    app_commands.Choice(name="Embedding", value="embedding"),
    app_commands.Choice(name="Jaccard", value="jaccard"),
    app_commands.Choice(name="Fusion", value="fusion"),
]

DEFAULT_TARGET_SIZE: dict[str, int] = {
    "magic": 60,
    "pokemon": 60,
    "yugioh": 40,
}


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

_http: httpx.AsyncClient | None = None


async def http() -> httpx.AsyncClient:
    global _http  # noqa: PLW0603
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(base_url=API_URL, timeout=30.0)
    return _http


async def api_get(path: str, **params: Any) -> dict[str, Any]:
    client = await http()
    resp = await client.get(path, params=params)
    resp.raise_for_status()
    return resp.json()


async def api_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    client = await http()
    resp = await client.post(path, json=body)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def game_color(game: str) -> discord.Color:
    return GAME_COLORS.get(game, discord.Color.blurple())


def truncate(text: str, limit: int = 4096) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def format_score(score: float) -> str:
    return f"{score:.3f}"


def _card_line(name: str, score: float | None = None, metadata: dict | None = None) -> str:
    """Format a single result card line."""
    parts: list[str] = []
    if score is not None:
        parts.append(f"`{format_score(score)}`")
    parts.append(f"**{name}**")
    if metadata:
        extras = []
        if metadata.get("type_line"):
            extras.append(metadata["type_line"])
        elif metadata.get("type"):
            extras.append(metadata["type"])
        if metadata.get("mana_cost"):
            extras.append(metadata["mana_cost"])
        if extras:
            parts.append(f"-- {', '.join(extras)}")
    return " ".join(parts)


def _image_url_from_metadata(metadata: dict | None) -> str | None:
    if not metadata:
        return None
    return metadata.get("image_url") or metadata.get("image_uris", {}).get("normal")


# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready() -> None:
    await tree.sync()
    print(f"Logged in as {client.user} (synced slash commands)")


# ---------------------------------------------------------------------------
# /similar
# ---------------------------------------------------------------------------


@tree.command(name="similar", description="Find cards similar to a given card")
@app_commands.describe(
    card_name="Card name to find similar cards for",
    game="Card game (default: magic)",
    mode="Similarity mode (default: synergy)",
    k="Number of results (default: 5)",
)
@app_commands.choices(game=GAME_CHOICES, mode=MODE_CHOICES)
async def similar_cmd(
    interaction: discord.Interaction,
    card_name: str,
    game: app_commands.Choice[str] | None = None,
    mode: app_commands.Choice[str] | None = None,
    k: int = 5,
) -> None:
    await interaction.response.defer()
    game_val = game.value if game else "magic"
    mode_val = mode.value if mode else "synergy"
    try:
        data = await api_get(
            f"/v1/cards/{card_name}/similar",
            game=game_val,
            use_case=mode_val,
            top_k=min(k, 25),
        )
    except httpx.HTTPStatusError as exc:
        await interaction.followup.send(
            embed=discord.Embed(
                title="Error",
                description=_http_error_message(exc),
                color=discord.Color.dark_red(),
            )
        )
        return
    except httpx.ConnectError:
        await interaction.followup.send(
            embed=discord.Embed(
                title="API Unavailable",
                description=f"Could not reach the DeckSage API at `{API_URL}`.",
                color=discord.Color.dark_red(),
            )
        )
        return

    results = data.get("results", [])
    lines = [_card_line(r["card"], r.get("similarity"), r.get("metadata")) for r in results]
    body = "\n".join(lines) if lines else "No results found."

    embed = discord.Embed(
        title=f"Cards similar to {data.get('query', card_name)}",
        description=truncate(body),
        color=game_color(game_val),
    )
    embed.set_footer(text=f"Game: {game_val} | Mode: {mode_val} | Results: {len(results)}")

    thumb = _image_url_from_metadata(data.get("query_metadata"))
    if thumb:
        embed.set_thumbnail(url=thumb)

    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /search
# ---------------------------------------------------------------------------


@tree.command(name="search", description="Search for cards by text query")
@app_commands.describe(
    query="Search query",
    game="Card game (default: magic)",
    limit="Max results (default: 5)",
)
@app_commands.choices(game=GAME_CHOICES)
async def search_cmd(
    interaction: discord.Interaction,
    query: str,
    game: app_commands.Choice[str] | None = None,
    limit: int = 5,
) -> None:
    await interaction.response.defer()
    game_val = game.value if game else "magic"
    try:
        data = await api_post(
            "/v1/search",
            {"game": game_val, "query": query, "limit": min(limit, 25)},
        )
    except httpx.HTTPStatusError as exc:
        await interaction.followup.send(
            embed=discord.Embed(
                title="Error",
                description=_http_error_message(exc),
                color=discord.Color.dark_red(),
            )
        )
        return
    except httpx.ConnectError:
        await interaction.followup.send(
            embed=discord.Embed(
                title="API Unavailable",
                description=f"Could not reach the DeckSage API at `{API_URL}`.",
                color=discord.Color.dark_red(),
            )
        )
        return

    results = data.get("results", [])
    lines = [_card_line(r["card_name"], r.get("score"), r.get("metadata")) for r in results]
    body = "\n".join(lines) if lines else "No results found."

    embed = discord.Embed(
        title=f'Search: "{query}"',
        description=truncate(body),
        color=game_color(game_val),
    )
    embed.set_footer(text=f"Game: {game_val} | Total: {data.get('total', len(results))}")
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /parse
# ---------------------------------------------------------------------------


@tree.command(name="parse", description="Parse a deck list from text")
@app_commands.describe(
    deck_text="Deck list text (one card per line, e.g. '4 Lightning Bolt')",
    game="Card game (default: magic)",
)
@app_commands.choices(game=GAME_CHOICES)
async def parse_cmd(
    interaction: discord.Interaction,
    deck_text: str,
    game: app_commands.Choice[str] | None = None,
) -> None:
    await interaction.response.defer()
    game_val = game.value if game else "magic"
    try:
        data = await api_post("/v1/deck/parse", {"text": deck_text, "game": game_val})
    except httpx.HTTPStatusError as exc:
        await interaction.followup.send(
            embed=discord.Embed(
                title="Error",
                description=_http_error_message(exc),
                color=discord.Color.dark_red(),
            )
        )
        return
    except httpx.ConnectError:
        await interaction.followup.send(
            embed=discord.Embed(
                title="API Unavailable",
                description=f"Could not reach the DeckSage API at `{API_URL}`.",
                color=discord.Color.dark_red(),
            )
        )
        return

    if data.get("error"):
        await interaction.followup.send(
            embed=discord.Embed(
                title="Parse Error",
                description=data["error"],
                color=discord.Color.dark_red(),
            )
        )
        return

    partitions = data.get("partitions", [])
    lines: list[str] = []
    total = 0
    for part in partitions:
        lines.append(f"**{part['name']}**")
        for card in part.get("cards", []):
            count = card.get("count", 1)
            total += count
            lines.append(f"  {count}x {card['name']}")
        lines.append("")

    body = "\n".join(lines) if lines else "No cards parsed."

    embed = discord.Embed(
        title="Parsed Deck",
        description=truncate(body),
        color=game_color(game_val),
    )
    embed.set_footer(text=f"Game: {game_val} | Total cards: {total}")
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /complete
# ---------------------------------------------------------------------------


@tree.command(name="complete", description="Complete a partial deck list")
@app_commands.describe(
    deck_text="Deck list text (one card per line, e.g. '4 Lightning Bolt')",
    game="Card game (default: magic)",
    target_size="Target deck size (default: 60 for magic/pokemon, 40 for yugioh)",
)
@app_commands.choices(game=GAME_CHOICES)
async def complete_cmd(
    interaction: discord.Interaction,
    deck_text: str,
    game: app_commands.Choice[str] | None = None,
    target_size: int | None = None,
) -> None:
    await interaction.response.defer()
    game_val = game.value if game else "magic"
    target = target_size or DEFAULT_TARGET_SIZE.get(game_val, 60)

    # Parse deck text first
    try:
        parsed = await api_post("/v1/deck/parse", {"text": deck_text, "game": game_val})
    except httpx.HTTPStatusError as exc:
        await interaction.followup.send(
            embed=discord.Embed(
                title="Error",
                description=_http_error_message(exc),
                color=discord.Color.dark_red(),
            )
        )
        return
    except httpx.ConnectError:
        await interaction.followup.send(
            embed=discord.Embed(
                title="API Unavailable",
                description=f"Could not reach the DeckSage API at `{API_URL}`.",
                color=discord.Color.dark_red(),
            )
        )
        return

    if parsed.get("error"):
        await interaction.followup.send(
            embed=discord.Embed(
                title="Parse Error",
                description=parsed["error"],
                color=discord.Color.dark_red(),
            )
        )
        return

    deck = {"partitions": parsed["partitions"]}

    # Complete the deck
    try:
        data = await api_post(
            "/v1/deck/complete",
            {"game": game_val, "deck": deck, "target_main_size": target},
        )
    except httpx.HTTPStatusError as exc:
        await interaction.followup.send(
            embed=discord.Embed(
                title="Error",
                description=_http_error_message(exc),
                color=discord.Color.dark_red(),
            )
        )
        return

    completed = data.get("deck", {})
    steps = data.get("steps", [])

    # Format the completed deck
    lines: list[str] = []
    total = 0
    for part in completed.get("partitions", []):
        lines.append(f"**{part['name']}**")
        for card in part.get("cards", []):
            count = card.get("count", 1)
            total += count
            lines.append(f"  {count}x {card['name']}")
        lines.append("")

    body = "\n".join(lines) if lines else "No deck returned."

    embed = discord.Embed(
        title="Completed Deck",
        description=truncate(body),
        color=game_color(game_val),
    )
    embed.set_footer(text=f"Game: {game_val} | Cards: {total} | Steps: {len(steps)}")
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def _http_error_message(exc: httpx.HTTPStatusError) -> str:
    """Extract a user-friendly message from an HTTP error."""
    status = exc.response.status_code
    try:
        detail = exc.response.json().get("detail", str(exc))
    except Exception:
        detail = exc.response.text[:200] if exc.response.text else str(exc)
    return f"API returned {status}: {detail}"


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN environment variable is required.", file=sys.stderr)
        sys.exit(1)
    client.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
