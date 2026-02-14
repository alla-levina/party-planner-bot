# Party Planner Bot

A Telegram bot for organizing parties. Guests coordinate who brings what — so nobody brings the same thing.

## Features

- **Create parties** with unique invite links (duplicate name prevention per owner)
- **Join parties** via shareable deep links
- **View contributions** — see what everyone is bringing
- **Add contributions** — claim what you're bringing with duplicate prevention
- **Edit contributions** — rename or remove your own contributions
- **Member list** — see who's in the party, search by name
- **Party info** — admins can set date/time (inline calendar + time picker), address, map link, and notes; all members are notified when info changes (debounced — rapid edits are batched into one message)
- **Location sharing** — share a Telegram location pin to auto-generate a Google Maps link
- **Admin roles** — admins can promote/demote other members and kick non-owners
- **Leave / cancel party** — members can leave, admins can delete the party

## Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather) and get your bot token.

2. Clone this repository and install dependencies:

```bash
cd maslenitsa-bot
pip install -r requirements.txt
```

3. Create a `.env` file from the example:

```bash
cp .env.example .env
```

4. Edit `.env` and set your bot token and PostgreSQL connection string:

```
BOT_TOKEN=your-telegram-bot-token-here
DATABASE_URL=postgresql://user:password@localhost:5432/partybot
```

5. Run the bot:

```bash
python -m bot.main
```

## Deployment (Railway)

1. Push the repo to GitHub
2. Create a project on [railway.app](https://railway.app) and deploy from GitHub
3. Add a PostgreSQL plugin to the project
4. Set `BOT_TOKEN` and `DATABASE_URL` as environment variables
5. Railway auto-deploys on every push

## Usage

- `/start` — Main menu: create a party or view your parties
- Share the invite link with friends so they can join your party
- Use inline buttons to manage contributions, members, and party info

## Dependencies

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) — Telegram Bot API wrapper
- [asyncpg](https://github.com/MagicStack/asyncpg) — PostgreSQL async driver
- [python-dotenv](https://github.com/theskumar/python-dotenv) — `.env` file loading
- [python-telegram-bot-calendar](https://github.com/artembakhanov/python-telegram-bot-calendar) — Inline calendar widget for date selection

## Project Structure

```
maslenitsa-bot/
  bot/
    main.py          — Entry point, handler registration
    config.py        — Environment config (BOT_TOKEN, DATABASE_URL)
    database.py      — PostgreSQL database layer (asyncpg)
    keyboards.py     — Inline keyboard builders (menus, calendar, time picker)
    utils.py         — Helpers (HTML escaping, code generation, display names)
    handlers/
      start.py       — /start, main menu, deep-link join
      party.py       — Create party, party menu, invite link, leave/cancel
      fillings.py    — View, add, edit, remove contributions
      members.py     — View, search, kick, promote/demote members
      party_info.py  — View/edit party info (date via calendar, address, map, notes, location pins)
  requirements.txt   — Python dependencies
  Procfile           — Railway process type
  runtime.txt        — Python version for Railway
  railway.toml       — Railway build/deploy config
```
