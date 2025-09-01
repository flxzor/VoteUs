import os
import random
import requests
import time
import json
import threading
import logging
import re
import toml
from typing import Optional

from endstone.plugin import Plugin
from endstone.command import CommandSender, Command, CommandSenderWrapper
from endstone import Player

logger = logging.getLogger("VoteUs")

# ---------------------------
# Configurable defaults
# ---------------------------
DEFAULT_CONFIG = {
    "api": {"server_key": ""},
    "reward": {"commands": ["give {player} diamond 1"], "cooldown": 86400},
    "messages": {
        "vote_link": "§a[VoteUs] §eVote for our server at §bhttps://minecraftpocket-servers.com/server/YOUR_ID/vote/",
        "reward_given": "§a[VoteUs] Thanks for voting! Here's your reward.",
        "not_voted": "§a[VoteUs] §cYou haven't voted today!",
        "already_claimed": "§a[VoteUs] §cYou already claimed your vote reward today!",
        "api_error": "§cAPI error, contact server owner.",
        "cooldown_remaining": "§a[VoteUs] §cYou can vote again in {h}h {m}m {s}s.",
        "reward_command_error": "§cError executing reward command.",
        "topvoters_header": "§6Top voters this month:",
        "topvoters_error": "§cFailed to fetch top voters."
    },
    "promo": {
        "messages": [
            "§a[VoteUs] §eVote & support us /vote!",
            "§a[VoteUs] §eGet rewards every vote!",
            "§a[VoteUs] §eYour vote means a lot!"
        ],
        "promo_interval_seconds": 120
    },
    "cache": {"votes_ttl_seconds": 120}
}

class VoteUsPlugin(Plugin):
    api_version = "0.10"
    load = "POSTWORLD"
    prefix = "[VoteUs]"

    commands = {
        "vote": {
            "description": "Show the voting link or execute admin subcommands",
            "usages": ["/vote", "/vote (help|reload|set)<action: VoteAction> [key: string]"],
            "permissions": ["voteus.command.vote"],
        },
        "claimvote": {
            "description": "Claim your voting reward",
            "usages": ["/claimvote"],
            "permissions": ["voteus.command.claimvote"],
        },
        "topvoters": {
            "description": "Show top voters this month",
            "usages": ["/topvoters"],
            "permissions": ["voteus.command.topvoters"],
        },
    }

    permissions = {
        "voteus.command.vote": {"description": "Allow users to use the /vote command", "default": True},
        "voteus.command.claimvote": {"description": "Allow users to use the /claimvote command", "default": True},
        "voteus.command.topvoters": {"description": "Allow users to use the /topvoters command", "default": True},
    }

    def on_load(self):
        self._lock = threading.RLock()
        self._data_folder = getattr(self, "data_folder", "./data/voteus")
        os.makedirs(self._data_folder, exist_ok=True)
        self._claims_path = os.path.join(self._data_folder, "claims.json")
        self._config_path = os.path.join(self._data_folder, "config.toml")

        # runtime state
        self._last_claim: dict[str, float] = {}
        self._votes_cache = {"names": set(), "ts": 0}

        # load config + claims
        self._load_or_create_config()
        self._load_claims()

    def _load_or_create_config(self):
        if not os.path.exists(self._config_path):
            try:
                with open(self._config_path, "w", encoding="utf-8") as f:
                    toml.dump(DEFAULT_CONFIG, f)
            except Exception as e:
                logger.error(f"Failed to create default config: {e}")

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                loaded = toml.load(f)
        except Exception as e:
            logger.error(f"Failed to parse config.toml: {e}")
            loaded = {}

        cfg = DEFAULT_CONFIG.copy()
        cfg.update(loaded or {})
        cfg["api"] = {**DEFAULT_CONFIG["api"], **(loaded.get("api", {}) if loaded else {})}
        cfg["reward"] = {**DEFAULT_CONFIG["reward"], **(loaded.get("reward", {}) if loaded else {})}
        cfg["messages"] = {**DEFAULT_CONFIG["messages"], **(loaded.get("messages", {}) if loaded else {})}
        cfg["promo"] = {**DEFAULT_CONFIG["promo"], **(loaded.get("promo", {}) if loaded else {})}
        cfg["cache"] = {**DEFAULT_CONFIG["cache"], **(loaded.get("cache", {}) if loaded else {})}

        self._config = cfg
        self._api_key = self._config["api"].get("server_key", "")

        if not self._api_key:
            logger.warning("VoteUs server key not found in config.toml!")

    def _load_claims(self):
        try:
            if os.path.exists(self._claims_path):
                with open(self._claims_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                with self._lock:
                    self._last_claim = {k: float(v) for k, v in data.items()}
            else:
                self._last_claim = {}
        except Exception as e:
            logger.error(f"Failed to load claims: {e}")
            self._last_claim = {}

    def _save_claims_async(self):
        """Spawn a background thread to persist claims (file I/O off main thread)."""
        def w(data, path):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception as e:
                logger.error(f"Failed to save claims: {e}")

        with self._lock:
            snapshot = dict(self._last_claim)
        now = time.time()
        if not hasattr(self, "_last_save") or now - self._last_save > 300:
            t = threading.Thread(target=w, args=(snapshot, self._claims_path), daemon=True)
            t.start()
            self._last_save = now

    # ---------------------
    # Scheduler wiring
    # ---------------------
    def on_enable(self):
        self.command_sender = CommandSenderWrapper(sender=self.server.command_sender, on_message=None)

        # schedule promo
        interval = int(self._config.get("promo", {}).get("promo_interval_seconds", 300))
        ticks = max(1, interval) * 20
        try:
            self.server.scheduler.run_task(self, self._promo_scheduler_wrapper, delay=0, period=ticks)
        except Exception as e:
            logger.warning(f"Failed to schedule promo task: {e}")

    def _promo_scheduler_wrapper(self):
        threading.Thread(target=self._promo_worker, daemon=True).start()

    def _promo_worker(self):
        msgs = self._config.get("promo", {}).get("messages", [])
        if not msgs:
            return
        message = random.choice(msgs)
        def do_broadcast():
            try:
                self.server.broadcast_message(message)
            except Exception as e:
                logger.warning(f"Failed to broadcast promo in main thread: {e}")
        try:
            self.server.scheduler.run_task(self, do_broadcast)
        except Exception as e:
            logger.warning(f"run_task not available, calling broadcast directly (risky): {e}")
            try:
                self.server.broadcast_message(message)
            except Exception:
                logger.exception("Direct broadcast failed.")

    # ---------------------
    # Core background workers
    # ---------------------
    def _safe_get_api_in_worker(self, url: str, retries: int = 2, timeout: int = 8) -> Optional[requests.Response]:
        """Safe blocking HTTP for background thread only. Returns Response or None."""
        for attempt in range(retries):
            try:
                resp = requests.get(url, timeout=timeout)
                if resp.status_code == 200:
                    return resp
                else:
                    logger.warning(f"API returned status {resp.status_code} for {url}")
            except Exception as e:
                logger.warning(f"API request failed ({attempt+1}/{retries}): {e}")
            time.sleep(1)
        return None

    # ---------------------
    # Helper utilities
    # ---------------------
    def _format_remaining(self, seconds: float) -> str:
        total = max(0, int(seconds))
        m, s = divmod(total, 60)
        h, m = divmod(m, 60)
        template = self._config.get("messages", {}).get("cooldown_remaining", "§a[VoteUs] §cYou can vote again in {h}h {m}m {s}s.")
        return template.format(h=h, m=m, s=s)

    def _extract_nicknames_from_votes_response(self, data) -> set:
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
        except Exception as e:
            logger.warning(f"Failed to parse votes response: {e}")
        return names

    def _validate_player_name(self, name: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9_]+", name))

    def _update_server_key_in_config_file(self, new_key: str) -> bool:
        path = self._config_path
        try:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = toml.load(f)
            except Exception:
                existing = {}
            if "api" not in existing:
                existing["api"] = {}
            existing["api"]["server_key"] = new_key
            with open(path, "w", encoding="utf-8") as f:
                toml.dump(existing, f)
            self._api_key = new_key
            self._config["api"]["server_key"] = new_key
            return True
        except Exception as e:
            logger.error(f"Failed to update config.toml server_key: {e}")
            return False

    # ---------------------
    # Command handling
    # ---------------------
    def on_command(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        messages = self._config.get("messages", {})

        if command.name == "vote":
            if not args:
                sender.send_message(messages.get("vote_link"))
                return True

            action = args[0].lower()
            if action == "help":
                help_text = (
                    "§a[VoteUs] Available commands:\n"
                    "§e/vote §7- Show voting link\n"
                    "§e/vote help §7- Show this help message\n"
                    "§e/vote reload §7- Reload config (console only)\n"
                    "§e/vote set <key> §7- Set server key (console only)\n"
                    "§e/claimvote §7- Claim your voting reward\n"
                    "§e/topvoters §7- Show top voters this month"
                )
                sender.send_message(help_text)
                return True

            elif action == "reload":
                if not isinstance(sender, Player):
                    self._load_or_create_config()
                    sender.send_message("§a[VoteUs] Config reloaded.")
                else:
                    sender.send_message("§cThis command can only be executed from console.")
                return True

            elif action == "set":
                if not isinstance(sender, Player):
                    if len(args) < 2:
                        sender.send_message("§cUsage: /vote set <key>")
                        return True
                    new_key = args[1]
                    if self._update_server_key_in_config_file(new_key):
                        sender.send_message("§a[VoteUs] Server key updated.")
                    else:
                        sender.send_message("§cFailed to update server key.")
                else:
                   sender.send_message("§cThis command can only be executed from console.")
                return True

            else:
                sender.send_message("§cInvalid subcommand. Use /vote help for available commands.")
                return True

        elif command.name == "claimvote":
            if not isinstance(sender, Player):
                sender.send_message("§cThis command can only be used in-game.")
                return True

            player_name = sender.name
            now = time.time()
            cooldown = int(self._config.get("reward", {}).get("cooldown", 86400))
            msgs = self._config.get("messages", {})

            with self._lock:
                last = float(self._last_claim.get(player_name, 0))

            if now - last < cooldown:
                remaining = cooldown - (now - last)
                sender.send_message(msgs.get("already_claimed"))
                sender.send_message(self._format_remaining(remaining))
                return True

            sender.send_message("§a[VoteUs] Checking vote status...")

            def claim_worker(name_snapshot):
                result = {"name": name_snapshot, "status": "api_error"}
                if not self._api_key:
                    self._schedule_claim_result(result)
                    return

                url1 = f"https://minecraftpocket-servers.com/api/?action=post&object=votes&element=claim&key={self._api_key}&username={name_snapshot}"
                try:
                    resp = requests.get(url1, timeout=8)
                    res_text = resp.text.strip()
                except Exception as e:
                    logger.warning(f"Claim API error for {name_snapshot}: {e}")
                    self._schedule_claim_result(result)
                    return

                if res_text == "1":
                    result["status"] = "granted"
                elif res_text == "0":
                    try:
                        resp2 = requests.get(
                            f"https://minecraftpocket-servers.com/api/?action=post&object=votes&element=claim&key={self._api_key}&username={name_snapshot.lower()}",
                            timeout=8
                        )
                        if resp2 and resp2.text.strip() == "1":
                            result["status"] = "granted"
                        else:
                            result["status"] = "not_voted"
                    except Exception:
                        result["status"] = "not_voted"
                else:
                    result["status"] = "already_claimed"

                self._schedule_claim_result(result)

            t = threading.Thread(target=claim_worker, args=(player_name,), daemon=True)
            t.start()
            return True

        elif command.name == "topvoters":
            if not self._api_key:
                sender.send_message(messages.get("api_error"))
                return True

            sender.send_message("§a[VoteUs] Fetching top voters...")

            def topvoters_worker(name_snapshot):
                url = f"https://minecraftpocket-servers.com/api/?object=servers&element=votes&key={self._api_key}&format=json"
                resp = self._safe_get_api_in_worker(url)
                result = {"status": "error", "voters": []}
                if not resp:
                    self._schedule_topvoters_result(name_snapshot, result)
                    return
                try:
                    data = resp.json()
                    voters = self._extract_nicknames_from_votes_response(data)
                    result["status"] = "ok"
                    result["voters"] = sorted(voters)
                except Exception as e:
                    logger.warning(f"Topvoters parse error: {e}")
                    result["status"] = "error"

                self._schedule_topvoters_result(name_snapshot, result)

            t = threading.Thread(target=topvoters_worker, args=(sender.name,), daemon=True)
            t.start()
            return True

        return True

    # ---------------------
    # Scheduling results back to main thread
    # ---------------------
    def _schedule_claim_result(self, result: dict):
        """Schedule handling of claim result on main thread."""
        def handle():
            name = result.get("name")
            status = result.get("status")
            msgs = self._config.get("messages", {})
            try:
                player_obj = self.server.get_player(name)
                if not player_obj:
                    return

                if status == "granted":
                    for cmd_tpl in self._config.get("reward", {}).get("commands", []):
                        cmd = cmd_tpl.format(player=name)
                        try:
                            self.server.dispatch_command(self.command_sender, cmd)
                        except Exception as e:
                            logger.error(f"Failed to execute command '{cmd}': {e}")
                            try:
                                player_obj.send_message(msgs.get("reward_command_error"))
                            except Exception:
                                pass
                    try:
                        player_obj.send_message(msgs.get("reward_given"))
                    except Exception:
                        pass
                    with self._lock:
                        self._last_claim[name] = time.time()
                    self._save_claims_async()
                elif status == "not_voted":
                    try:
                        player_obj.send_message(msgs.get("not_voted"))
                    except Exception:
                        pass
                elif status == "already_claimed":
                    try:
                        player_obj.send_message(msgs.get("already_claimed"))
                    except Exception:
                        pass
                else:
                    try:
                        player_obj.send_message(msgs.get("api_error"))
                    except Exception:
                        pass
            except Exception:
                logger.exception("Failed in claim result handler")

        try:
            self.server.scheduler.run_task(self, handle)
        except Exception as e:
            logger.warning(f"run_task unavailable; attempting direct call (risky): {e}")
            try:
                handle()
            except Exception:
                logger.exception("Direct claim handler failed")

    def _schedule_topvoters_result(self, requester_name: str, result: dict):
        """Schedule topvoters response to be sent to the requesting player on main thread."""
        def handle():
            msgs = self._config.get("messages", {})
            name = requester_name
            try:
                player_obj = self.server.get_player(name)
                if not player_obj:
                    return
                if result.get("status") != "ok":
                    player_obj.send_message(msgs.get("topvoters_error"))
                    return
                voters = result.get("voters", [])[:5]
                player_obj.send_message(msgs.get("topvoters_header"))
                for i, v in enumerate(voters, 1):
                    player_obj.send_message(f"§e{i}. §b{v}")
            except Exception:
                logger.exception("Failed to send topvoters result")

        try:
            self.server.scheduler.run_task(self, handle)
        except Exception as e:
            logger.warning(f"run_task unavailable; attempting direct call (risky): {e}")
            try:
                handle()
            except Exception:
                logger.exception("Direct topvoters handler failed")