import os
import random
import tomllib
import requests
import time
import json
from endstone.plugin import Plugin
from endstone.command import CommandSender, Command, CommandSenderWrapper
from endstone import Player

class VoteUsPlugin(Plugin):
    api_version = "0.10"
    load = "POSTWORLD"
    prefix = "[VoteUs]"

    commands = {
        "vote": {
            "description": "Show the voting link",
            "usages": ["/vote"],
            "permissions": []
        },
        "claimvote": {
            "description": "Claim your voting reward",
            "usages": ["/claimvote"],
            "permissions": []
        },
        "topvoters": {
            "description": "Show top voters this month",
            "usages": ["/topvoters"],
            "permissions": []
        }
    }

    def on_load(self) -> None:
        self.load_config()

    def load_config(self) -> None:
        path = os.path.join(self.data_folder, "config.toml")
        default = """\
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
"""
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(default)

        with open(path, "rb") as f:
            self._config = tomllib.load(f)

        # Initialize runtime state
        self._last_claim = {}
        self._pending_votes = set()
        self._claims_path = os.path.join(self.data_folder, "claims.json")
        self._load_claims()

    def _load_claims(self) -> None:
        try:
            if os.path.exists(self._claims_path):
                with open(self._claims_path, "r", encoding="utf-8") as f:
                    self._last_claim = json.load(f)
                    for k, v in list(self._last_claim.items()):
                        try:
                            self._last_claim[k] = float(v)
                        except Exception:
                            self._last_claim.pop(k, None)
            else:
                self._last_claim = {}
        except Exception:
            self._last_claim = {}

    def _save_claims(self) -> None:
        try:
            with open(self._claims_path, "w", encoding="utf-8") as f:
                json.dump(self._last_claim, f)
        except Exception:
            pass

    def on_enable(self) -> None:
        self.command_sender = CommandSenderWrapper(
            sender=self.server.command_sender,
            on_message=None
        )
        interval = self._config.get("promo", {}).get("promo_interval_seconds", 120)
        ticks = max(1, int(interval)) * 20
        self.server.scheduler.run_task(self, self.broadcast_promo, delay=0, period=ticks)

        auto_interval = self._config.get("autocheck", {}).get("interval_seconds", 60)
        auto_ticks = max(10, int(auto_interval)) * 20
        self.server.scheduler.run_task(self, self._auto_detect_votes, delay=auto_ticks, period=auto_ticks)

    def on_disable(self) -> None:
        self._save_claims()

    def broadcast_promo(self) -> None:
        msgs = self._config.get("promo", {}).get("messages", [])
        if not msgs or not self.server.online_players:
            return
        promo = random.choice(msgs)
        self.server.broadcast_message(promo)

    def _format_remaining(self, seconds: float) -> str:
        total = max(0, int(seconds))
        m, s = divmod(total, 60)
        h, m = divmod(m, 60)
        template = self._config.get("messages", {}).get("cooldown_remaining",
                                                       "§a[VoteUs] §cYou can vote again in {h}h {m}m {s}s.")
        return template.format(h=h, m=m, s=s)

    def _extract_nicknames_from_votes_response(self, data):
        # idk im not sure about the structure
        names = set()
        try:
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        names.add(item.lower())
                    elif isinstance(item, dict):
                        for key in ("nickname", "nick", "player", "username", "name"):
                            if key in item and item[key]:
                                names.add(str(item[key]).lower())
                                break
            elif isinstance(data, dict):
                for candidate in ("votes", "players", "voters", "latest", "data"):
                    if candidate in data:
                        return self._extract_nicknames_from_votes_response(data[candidate])
                for k in data.keys():
                    if isinstance(k, str):
                        names.add(k.lower())
        except Exception:
            pass
        return names

    def _auto_detect_votes(self) -> None:
        api_key = self._config["api"]["server_key"]
        msgs = self._config.get("messages", {})
        try:
            resp = requests.get(
                f"https://minecraftpocket-servers.com/api/?object=servers&element=votes&key={api_key}&format=json",
                timeout=8
            )
            if resp.status_code != 200:
                return
            data = resp.json()
            voted_names = self._extract_nicknames_from_votes_response(data)
            if not voted_names:
                return

            cooldown = self._config["reward"]["cooldown"]
            now = time.time()
            for player in list(self.server.online_players):
                try:
                    name = player.name
                    lname = name.lower()
                    last = float(self._last_claim.get(name, 0))
                    if now - last < cooldown or name in self._pending_votes:
                        continue
                    if lname in voted_names:
                        self._pending_votes.add(name)
                        player.send_message(msgs.get("vote_detected",
                                                    "§a[VoteUs]Use §e/claimvote §ato claim your reward."))
                except Exception:
                    pass
        except Exception:
            pass

    def on_command(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        if not isinstance(sender, Player):
            sender.send_message("This command is for players only.")
            return True

        name = sender.name
        now = time.time()
        api_key = self._config["api"]["server_key"]
        msgs = self._config["messages"]
        cooldown = self._config["reward"]["cooldown"]

        if command.name == "vote":
            sender.send_message(msgs.get("vote_link"))
            return True

        if command.name == "claimvote":
            last = float(self._last_claim.get(name, 0))
            if now - last < cooldown:
                remaining = cooldown - (now - last)
                sender.send_message(msgs.get("already_claimed"))
                sender.send_message(self._format_remaining(remaining))
                return True

            try:
                resp = requests.get(
                    f"https://minecraftpocket-servers.com/api/?action=post&object=votes&element=claim&key={api_key}&username={name}",
                    timeout=8
                )
                res = resp.text.strip()
                if res == "0":
                    resp = requests.get(
                        f"https://minecraftpocket-servers.com/api/?action=post&object=votes&element=claim&key={api_key}&username={name.lower()}",
                        timeout=8
                    )
                    res = resp.text.strip()
            except Exception:
                sender.send_message(msgs.get("api_error"))
                return True

            if res == "1":
                for cmd_tpl in self._config["reward"]["commands"]:
                    cmd = cmd_tpl.format(player=name)
                    try:
                        self.server.dispatch_command(self.command_sender, cmd)
                    except Exception:
                        sender.send_message(msgs.get("reward_command_error", "§cError executing reward command."))
                sender.send_message(msgs.get("reward_given"))
                self._last_claim[name] = now
                self._save_claims()
                self._pending_votes.discard(name)
            elif res == "0":
                sender.send_message(msgs.get("not_voted"))
            else:
                sender.send_message(msgs.get("already_claimed"))
            return True

        if command.name == "topvoters":
            try:
                resp = requests.get(
                    f"https://minecraftpocket-servers.com/api/?object=servers&element=voters&key={api_key}&month=current&format=json",
                    timeout=8
                )
                data = resp.json()
                sender.send_message(msgs.get("topvoters_header", "§6Top voters this month:"))
                for i, v in enumerate(data.get("voters", []), start=1):
                    sender.send_message(f"{i}. {v.get('nickname', v.get('nick', 'Unknown'))} – {v.get('votes', 0)} votes")
            except Exception:
                sender.send_message(msgs.get("topvoters_error", "§cFailed to fetch top voters."))
            return True

        return False
