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
You can set server key in here:

```toml
[api]
server_key = "YOUR_SERVER_KEY"

```

You can set the reward in here:
```toml
[reward]
commands = [ "give {player} diamond 1"]
cooldown = 86400 #24h
```

## Commands
- `/claimvote`: Claim rewards after voting.
- `/vote` : Show the voting link.
- `/topvoters` : Show top voters in this month.
- `/vote set <Server Key>` : set your server key.
- `/vote reload` : reload config.
- `/vote help` : show the help 

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
