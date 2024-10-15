import datetime
import re
import time

import requests
from bs4 import BeautifulSoup
from django.core.management import BaseCommand
from django.utils import timezone

from zh.models import JobRun, Match, MatchPlayer, Player

LOGS = []


def log(message):
    message = f"[{timezone.now().isoformat()}] {message}"
    LOGS.append(message)
    print(message)


def update_run_status(job_run, start_time, loaded_matches):
    job_run.duration = datetime.timedelta(seconds=int(time.time() - start_time))
    job_run.loaded_matches = loaded_matches
    job_run.logs.extend(LOGS)
    LOGS.clear()
    job_run.save()


class GenToolClient:
    def __init__(self):
        self.base_url = "https://gentool.net/data/zh"

    def _get_links(self, data, extension=None):
        soup = BeautifulSoup(data, "html.parser")
        return [
            link["href"].strip("/")
            for link in soup.find_all("a")
            if not link.find_parent("th")
            and not any(prefix in link["href"] for prefix in ("data", "logs"))
            and (extension is None or link["href"].endswith(extension))
        ]

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
            "match_date": r"Match Date \(UTC\):\s+(.+)",
            "replay_size": r"\.rep \[(\d+) bytes\]",
        }

        # Extract individual fields using regex
        for key, pattern in patterns.items():
            match = re.search(pattern, data)
            value = match.group(1) if match else None

            if key == "match_date" and value:
                try:
                    value = datetime.strptime(value, "%Y %b %d, %H:%M:%S")
                except ValueError as e:
                    print(f"Error parsing date: {e}")
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

    def list_months(self, min_month=None):
        log(f"Listing months from {self.base_url} with {min_month=}")
        result = sorted(self._get_links(requests.get(f"{self.base_url}").text))
        if min_month:
            result = result[result.index(min_month) :]  # NOQA E203
        return result

    def list_days(self, month, min_month=None, min_day=None):
        url = f"{self.base_url}/{month}"
        log(f"Listing days from {url} with {min_month=} and {min_day=}")
        result = sorted(self._get_links(requests.get(url).text))
        if min_day and min_month and min_month == month:
            result = result[result.index(min_day) :]  # NOQA E203
        return result

    def list_players(self, month, day):
        url = f"{self.base_url}/{month}/{day}"
        log(f"Listing players from {url}")
        return self._get_links(requests.get(url).text)

    def list_matches(self, month, day, player):
        url = f"{self.base_url}/{month}/{day}/{player}"
        log(f"Listing matches from {url}")
        return self._get_links(requests.get(url).text, ".txt")

    def get_match_data(self, month, day, player, match):
        url = f"{self.base_url}/{month}/{day}/{player}/{match}"
        log(f"Getting match data from {url}")
        return self._parse_replay_data(requests.get(url).text)


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        gentool = GenToolClient()
        start_time = time.time()
        loaded_matches = 0
        previous_run = JobRun.objects.order_by("-start_time").first()
        if previous_run:
            min_month = previous_run.last_loaded_month
            min_day = previous_run.last_loaded_date
        else:
            min_month = None
            min_day = None

        current_run = JobRun.objects.create(
            start_time=timezone.now(), duration=None, success=False
        )

        try:
            for month in gentool.list_months(min_month):
                current_run.last_loaded_month = month
                for day in gentool.list_days(month, min_month, min_day):
                    current_run.last_loaded_date = day
                    for player_data in gentool.list_players(month, day):
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

                        for match_info in gentool.list_matches(month, day, player_data):
                            match_data = gentool.get_match_data(
                                month, day, player_data, match_info
                            )
                            match_players = match_data.pop("players")
                            replay_url = f"{gentool.base_url}/{month}/{day}/{player_data}/{match_info}".replace(  # NOQA E501
                                ".txt", ".rep"
                            )

                            if not Match.objects.filter(replay_url=replay_url).exists():
                                match = Match.objects.create(
                                    job_run=current_run,
                                    replay_url=replay_url,
                                    **match_data,
                                    replay_uploaded_by=player,
                                )

                                match_player_objects = []
                                for match_player in match_players:
                                    if match_player["player_name"] == player.player_name:
                                        player_object = player
                                    else:
                                        player_object, created_object = (
                                            Player.objects.get_or_create(  # NOQA E501
                                                name=match_player["player_name"]
                                            )
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
                                        f"Added player: {match_player['name']} to match: {replay_url}"  # NOQA E501
                                    )

                                MatchPlayer.objects.bulk_create(match_player_objects)
                                loaded_matches += 1
                    update_run_status(current_run, start_time, loaded_matches)
            current_run.success = True
        except Exception as e:
            current_run.success = False
            log(f"Error: {e}")

        update_run_status(current_run, start_time, loaded_matches)
