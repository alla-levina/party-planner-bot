# Maslenitsa Party Bot

A Telegram bot for organizing Maslenitsa (pancake celebration) parties. Guests coordinate fillings so nobody brings duplicates.

## Features

- **Create parties** with unique invite links
- **Join parties** via shareable deep links
- **View fillings** — see what everyone is bringing
- **Add fillings** — claim a filling with duplicate prevention
- **Edit fillings** — rename or remove your own fillings
- **Member list** — see who's in the party
- **Admin roles** — owner can promote/demote admins, admins can kick members
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
DATABASE_URL=postgresql://user:password@localhost:5432/maslenitsa
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
- Use inline buttons to manage fillings and members

## Project Structure

```
maslenitsa-bot/
  bot/
    main.py          — Entry point
    config.py        — Environment config
    database.py      — PostgreSQL database layer (asyncpg)
    keyboards.py     — Inline keyboard builders
    utils.py         — Helpers (code generation, etc.)
    handlers/
      start.py       — /start, main menu, deep link join
      party.py       — Create party, party menu, invite link
      fillings.py    — View, add, edit, remove fillings
      members.py     — View, search, kick, promote/demote members
```
