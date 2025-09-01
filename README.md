# VoteUs — Endstone Plugin (Python)

> **⚠️ IMPORTANT:**  
> **VoteUs Plugin** is currently **UNDER DEVELOPMENT**.  
> Features are not final, bugs are expected, and testing/feedback is appreciated!

![GitHub Release](https://img.shields.io/github/v/release/flxzor/VoteUs)

![GitHub Downloads (all assets, latest release)](https://img.shields.io/github/downloads/flxzor/VoteUs/latest/total)


A simple plugin to reward players for voting on Minecraft server listing sites [MinecraftPocket-Servers.com](https://minecraftpocket-servers.com). Built for **Endstone (Python)**.

---

## Installation
1. Download the latest `.whl` file from [GitHub Releases](https://github.com/flxzor/VoteUs/releases) and place it in your server's `plugins/` folder.  
2. Restart the server.

---

## Configuration
A `config.toml` file is automatically created if it does not exist.  
Here is an example:

```toml
[api]
server_key = "YOUR_SERVER_KEY"

[reward]
commands = ["give {player} minecraft:diamond 1"]
cooldown = 86400

[messages]
vote_link = "§a[VoteUs] §eVote for our server at §bhttps://minecraftpocket-servers.com/server/YOUR_ID/vote/"
reward_given = "§a[VoteUs] Thanks for voting! Here's your reward."
not_voted = "§a[VoteUs] §cYou haven't voted today!"
already_claimed = "§a[VoteUs] §cYou already claimed your vote reward today!"
api_error = "§cAPI error, contact server owner."
cooldown_remaining = "§a[VoteUs] §cYou can vote again in {h}h {m}m {s}s."
vote_detected = "§a[VoteUs] Use §e/claimvote §ato claim your reward."
reward_command_failed = "§cFailed to execute reward command."
reward_command_error = "§cError executing reward command."
topvoters_header = "§6Top voters this month:"
topvoters_error = "§cFailed to fetch top voters."

[promo]
messages = [
  "§a[VoteUs] §eVote & support us /vote!",
  "§a[VoteUs] §eGet rewards every vote!",
  "§a[VoteUs] §eYour vote means a lot!"
]
promo_interval_seconds = 120

[autocheck]
interval_seconds = 60
```

## Commands
- `/claimvote`: Claim rewards after voting.
- `/vote` : Show the voting link.
- `/topvoters` : Show top voters in this month

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
