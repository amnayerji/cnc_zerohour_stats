import datetime
import re
import time

import requests
from bs4 import BeautifulSoup
from dateutil.parser import isoparse
from django.core.management import BaseCommand
from django.db.models import Min
from django.utils import timezone

from zh.models import JobRun, Match, MatchPlayer, Player

LOGS = []


def log(message):
    message = f"[{timezone.now().isoformat()}] {message}"
    print(message)
    return
    LOGS.append(message)


class GenToolClient:
    def __init__(self):
        self.base_url = "https://gentool.net/data/zh"

    def _get_links(self, data, extension=None, minimum_timestamp=datetime.datetime.min):
        soup = BeautifulSoup(data, "html.parser")
        results = {}
        for link in soup.find_all("a"):
            name = link["href"].strip("/")
            if link.find_parent("th") or any(prefix in name for prefix in ("data", "logs")):
                continue
            if extension and not name.endswith(extension):
                continue
            row = link.find_parent("tr")
            timestamp = isoparse(f"{row.find_all('td')[2].text.strip()}:00")  # NOQA E231
            if timestamp is None or timestamp >= minimum_timestamp:
                results[name] = timestamp

        return dict(sorted(results.items(), key=lambda item: item[1]))  # Sort by timestamp

    def _parse_replay_data(self, data):
        # Initialize the dictionary to store extracted fields
        extracted_data = {}

        # Define regex patterns for the required fields
        patterns = {
            "game_version": r"Game Version:\s+Zero Hour ([\d.]+)",
            "map": r"Map Name:\s+(?:maps/)?(.+)",
            "starting_cash": r"Start Cash:\s+(\d+)",
            "match_length": r"Match Length:\s+([\d:]+)",
            "match_type": r"Match Type:\s+(.+)",
            "match_timestamp": r"Match Date \(UTC\):\s+(.+)",
            "replay_size": r"\.rep \[(\d+) bytes\]",
        }

        # Extract individual fields using regex
        for key, pattern in patterns.items():
            match = re.search(pattern, data)
            value = match.group(1) if match else None

            if key == "match_timestamp" and value:
                try:
                    value = datetime.datetime.strptime(value, "%Y %b %d, %H:%M:%S").astimezone(
                        datetime.timezone.utc
                    )
                except ValueError as e:
                    log(f"Error parsing date: {e}")
                    value = None
            if key == "game_version" and not value:
                value = "Unknown"

            if key == "rep_file_size" and value:
                value = int(value) / 1024  # Convert file size to an integer in KB

            extracted_data[key] = value

        # Regex patterns for teams and players
        team_pattern = r"Team (\d+)\n((?:\s+\S+ -?\S+ \([^)]+\)\n?)+)"
        player_pattern = r"^\s*\S+\s+(-?\S+)\s\(([^)]+)\)$"

        # Extract teams and players
        teams = {}
        for team_match in re.finditer(team_pattern, data, re.MULTILINE):
            team_number = int(team_match.group(1))
            team_players = team_match.group(2)

            players = re.findall(player_pattern, team_players, re.MULTILINE)
            teams[team_number] = [{"player_name": name, "army": army} for name, army in players]

        # Extract players without a team (if any)
        no_team_section = data.split("Team ")[0]
        no_team_players = re.findall(player_pattern, no_team_section, re.MULTILINE)

        # Prepare the final list of players
        extracted_data["players"] = []

        # Add team players to the final list
        for team_number, players in teams.items():
            for player in players:
                player["team"] = team_number
                extracted_data["players"].append(player)

        # Add no-team players (with team set to None)
        for name, army in no_team_players:
            extracted_data["players"].append({"player_name": name, "army": army, "team": None})

        return extracted_data

    def list_months(self, minimum_timestamp=None):
        log(f"Listing months from {self.base_url} with {minimum_timestamp=}")
        ignored_months = (
            "2024_04_April",
            "2024_05_May",
            "2024_06_June",
            "2024_07_July",
        )
        return [
            m
            for m in list(sorted(self._get_links(requests.get(f"{self.base_url}").text).keys()))
            if m not in ignored_months
        ]

    def list_days(self, month, minimum_timestamp=None):
        url = f"{self.base_url}/{month}"
        log(f"Listing days from {url} with {minimum_timestamp=}")
        return list(sorted(self._get_links(requests.get(url).text)))

    def list_players(self, month, day, minimum_timestamp=None):
        url = f"{self.base_url}/{month}/{day}"
        log(f"Listing players from {url} with {minimum_timestamp=}")
        return self._get_links(requests.get(url).text)

    def list_matches(self, month, day, player, minimum_timestamp=None):
        url = f"{self.base_url}/{month}/{day}/{player}"
        log(f"Listing matches from {url} with minimum_timestamp={minimum_timestamp}")
        return self._get_links(requests.get(url).text, ".txt")

    def get_match_data(self, month, day, player, match):
        url = f"{self.base_url}/{month}/{day}/{player}/{match}"
        log(f"Getting match data from {url}")
        return self._parse_replay_data(requests.get(url).text)


class Command(BaseCommand):
    def __init__(self):
        self.gentool = GenToolClient()
        self.start_time = time.time()
        self.loaded_matches = 0
        self.last_loaded_timestamp = None
        self.logs = []

    def _update_run_status(self):
        self.current_run.duration = datetime.timedelta(seconds=int(time.time() - self.start_time))
        self.current_run.loaded_matches = self.loaded_matches
        self.current_run.logs.extend(LOGS)
        self.current_run.save()
        LOGS.clear()

    def _process_match(
        self,
        month,
        day,
        player_data,
        player,
        match_info,
        replay_upload_timestamp,
    ):
        match_data = self.gentool.get_match_data(month, day, player_data, match_info)
        match_players = match_data.pop("players")
        replay_url = f"{self.gentool.base_url}/{month}/{day}/{player_data}/{match_info}".replace(
            # NOQA E501
            ".txt",
            ".rep",
        )

        if Match.objects.filter(replay_url=replay_url).exists():
            return
        match = Match.objects.create(
            job_run=self.current_run,
            replay_url=replay_url,
            replay_uploaded_by=player,
            replay_upload_timestamp=replay_upload_timestamp,
            **match_data,
        )
        log(f"Created match: {replay_url}")

        match_player_objects = []
        for match_player in match_players:
            if match_player["player_name"] == player.player_name:
                player_object = player
            else:
                player_object, created_object = Player.objects.get_or_create(  # NOQA E501
                    player_name=match_player["player_name"]
                )
                if created_object:
                    log(f"Created player: {match_player['player_name']}")
            match_player_objects.append(
                MatchPlayer(
                    match=match,
                    player=player_object,
                    team=match_player["team"],
                    army=match_player["army"],
                )
            )
            log(
                f"Adding player: {match_player['player_name']} to match: {replay_url}"  # NOQA E501
            )

        MatchPlayer.objects.bulk_create(match_player_objects)

    def _process_day(self, month, day, player_data):
        parts = player_data.split("_")
        gentool_id = parts[-1]
        name = "_".join(parts[:-1])

        try:
            player = Player.objects.get(gentool_id=gentool_id)
        except Player.DoesNotExist:
            player, created = Player.objects.get_or_create(player_name=name)
            if created:
                log(f"Created player: {name}")

        if not player.gentool_id:
            player.gentool_id = gentool_id
            player.save()
            log(f"Updated player: {name} with {gentool_id=}")

        for match_info, replay_upload_timestamp in self.gentool.list_matches(
            month, day, player_data, minimum_timestamp=self.last_loaded_timestamp
        ).items():
            self._process_match(
                month, day, player_data, player, match_info, replay_upload_timestamp
            )
            self.loaded_matches += 1
            self._update_run_status()

    def _process_players(self, month, day):
        for player_data in self.gentool.list_players(
            month, day, minimum_timestamp=self.last_loaded_timestamp
        ):
            self._process_day(month, day, player_data)

    def handle(self, *args, **kwargs):
        self.last_loaded_timestamp = Match.objects.aggregate(Min("replay_upload_timestamp"))[
            "replay_upload_timestamp__min"
        ]

        self.current_run = JobRun.objects.create(
            start_time=timezone.now(),
            duration=None,
            success=False,
        )

        try:
            for month in self.gentool.list_months(minimum_timestamp=self.last_loaded_timestamp):
                for day in self.gentool.list_days(
                    month, minimum_timestamp=self.last_loaded_timestamp
                ):
                    self._process_players(month, day)
            self.current_run.success = True
        except Exception as e:
            self.current_run.success = False
            log(f"Error: {e}")

        self._update_run_status()
