# VoteUs — Endstone Plugin (Python)

A simple plugin to reward players for voting on voting sites (e.g., MCPS). Designed to run on Endstone (Python) with optimizations to avoid burdening the main thread.

## Features
- Check vote status via external API (background thread)
- Provide rewards through server commands when a vote is valid
- Reuse HTTP session, pending-checks & lock, and client-side cooldown to reduce server load
- Periodic promotional broadcasts

## Installation
1. Download the latest `.whl` file from [GitHub Releases](https://github.com/flxzor/VoteUs/releases) and place it in the `plugins/` folder.
2. Restart the server.

## Configuration
A `config.toml` file will be automatically created if it doesn't exist. Example configuration:

```
[api]
server_key = "YOUR_SERVER_KEY"
check_url = "https://minecraftpocket-servers.com/api/"

[reward]
commands = [
  "give {player} diamond 1",
  "say Thanks {player}, you just voted!"
]
cooldown = 86400

[messages]
already_voted = "§cYou have already claimed your reward today!"
reward_given = "§aThanks for voting! Here's your reward."
not_voted = "§cYou haven't voted yet."
api_error = "§cFailed to check voting status. Try again later."
api_not_set = "§cVoting API not configured. Contact the server owner."

[voting]
cleanup_interval = 60
```

Ensure `server_key` and `check_url` are set according to the voting service used.

## Commands
- `/claimvote` or `/vote`: Claim rewards after voting.

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.