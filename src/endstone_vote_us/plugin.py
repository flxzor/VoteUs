import os
import random
import tomllib
import requests
import threading
import time
from typing import Dict, List, Set, Optional
from endstone.plugin import Plugin
from endstone import Player
from endstone.command import CommandSender, Command


class VoteUsPlugin(Plugin):
    api_version = "0.10"
    load = "POSTWORLD"
    prefix = "[VoteUs]"

    commands = {
        "claimvote": {"description": "Claim your voting reward", "usages": ["/claimvote"], "permissions": []},
        "vote": {"description": "Check your voting status", "usages": ["/vote"], "permissions": []}
    }
    permissions = {}

    voteus_config: Dict
    _last_claim: Dict[str, float]
    session: Optional[requests.Session]
    _pending_checks: Set[str]
    _lock: threading.Lock

    def on_load(self) -> None:
        self.logger.info(f"{self.prefix} Loading config...")
        self.load_config()
        self.session = requests.Session()
        self._pending_checks = set()
        self._lock = threading.Lock()

    def load_config(self) -> None:
        cfg_path = os.path.join(self.data_folder, "config.toml")
        default_cfg = """\
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
api_not_set = "§cVoting API not configured. Contact server owner."
promo_messages = [
  "§eVote server on MCPS & get cool reward!",
  "§bVote daily for bonuses!",
  "§eSupport us & vote today!"
]

[voting]
cleanup_interval = 60
"""
        if not os.path.exists(cfg_path):
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(default_cfg)
            self.logger.info(f"{self.prefix} Default config.toml created.")

        with open(cfg_path, "rb") as f:
            self.voteus_config = tomllib.load(f)
        self.logger.info(f"{self.prefix} Config loaded successfully.")
        self._last_claim = {}

    def on_enable(self) -> None:
        self.logger.info(f"{self.prefix} Plugin enabled.")
        api = self.voteus_config.get("api", {})
        if not api.get("server_key") or api["server_key"] == "YOUR_SERVER_KEY":
            self.logger.error(f"{self.prefix} server_key not set in config.toml!")
        if not api.get("check_url"):
            self.logger.error(f"{self.prefix} check_url not set in config.toml!")

        # Schedule promo broadcast every 2 minutes (2400 ticks)
        self.server.scheduler.run_task(self, self.broadcast_promo, delay=0, period=2400)

    def on_disable(self) -> None:
        self.logger.info(f"{self.prefix} Plugin disabled.")
        try:
            if self.session:
                self.session.close()
        except Exception:
            pass

    def broadcast_promo(self) -> None:
        promos = self.voteus_config.get("messages", {}).get("promo_messages", [])
        if not promos or not self.server.online_players:
            return
        promo = random.choice(promos)
        self.server.broadcast_message(promo)

    def on_command(self, sender: CommandSender, command: Command, args: List[str]) -> bool:
        if not isinstance(sender, Player):
            sender.send_message("This command is only for players.")
            return True

        cmd = command.name.lower()
        if cmd in ("claimvote", "vote"):
            return self.handle_vote(sender)
        return False

    def handle_vote(self, player: Player) -> bool:
        api = self.voteus_config.get("api", {})
        msg = self.voteus_config.get("messages", {})
        reward_cfg = self.voteus_config.get("reward", {})
        cooldown = reward_cfg.get("cooldown", 86400)

        if not api.get("server_key") or api["server_key"] == "YOUR_SERVER_KEY" or not api.get("check_url"):
            player.send_message(msg.get("api_not_set"))
            return True

        now = time.time()
        last = self._last_claim.get(player.name, 0)
        if now - last < cooldown:
            player.send_message(msg.get("already_voted"))
            return True

        with self._lock:
            if player.name in self._pending_checks:
                player.send_message("§ePlease wait, checking your vote status...")
                return True
            self._pending_checks.add(player.name)

        # perform network call in background thread to avoid blocking server main thread
        threading.Thread(target=self._check_vote, args=(player.name,), daemon=True).start()
        player.send_message("§eChecking vote status...")
        return True

    def _check_vote(self, player_name: str) -> None:
        api = self.voteus_config.get("api", {})
        msg = self.voteus_config.get("messages", {})
        url = f"{api['check_url']}?action=post&object=votes&element=claim&key={api['server_key']}&username={player_name}"
        res_text = None
        try:
            sess = self.session or requests.Session()
            resp = sess.get(url, timeout=5)
            if resp.status_code != 200:
                self.logger.error(f"{self.prefix} API returned HTTP {resp.status_code} for {player_name}")
                self.server.scheduler.run_task(self, lambda: self._send_player_message(player_name, msg.get("api_error")), delay=0)
                return
            res_text = resp.text.strip()
            self.logger.info(f"{self.prefix} API response for {player_name}: {res_text}")
        except Exception as e:
            self.logger.error(f"{self.prefix} HTTP error for {player_name}: {e}")
            self.server.scheduler.run_task(self, lambda: self._send_player_message(player_name, msg.get("api_error")), delay=0)
            return
        finally:
            with self._lock:
                self._pending_checks.discard(player_name)

        # schedule result handling on main thread
        if res_text == "1":
            self.server.scheduler.run_task(self, lambda: self._give_reward(player_name), delay=0)
        elif res_text == "0":
            self.server.scheduler.run_task(self, lambda: self._send_player_message(player_name, msg.get("not_voted")), delay=0)
        else:
            # treat any other response as already claimed / not eligible
            self.server.scheduler.run_task(self, lambda: self._send_player_message(player_name, msg.get("already_voted")), delay=0)

    def _find_online_player(self, name: str) -> Optional[Player]:
        for p in self.server.online_players:
            if p.name == name:
                return p
        return None

    def _send_player_message(self, player_name: str, message: str) -> None:
        p = self._find_online_player(player_name)
        if p and message:
            p.send_message(message)

    def _give_reward(self, player_name: str) -> None:
        player = self._find_online_player(player_name)
        if not player:
            self.logger.info(f"{self.prefix} Player {player_name} not online when applying reward.")
            return

        for cmd_tpl in self.voteus_config["reward"]["commands"]:
            cmd_str = cmd_tpl.format(player=player.name)
            self.server.dispatch_command(self.server.console_sender, cmd_str)

        msg = self.voteus_config.get("messages", {})
        player.send_message(msg.get("reward_given"))
        self._last_claim[player.name] = time.time()
