import unittest
from unittest.mock import patch

import pandas as pd

from padel_pipeline import (
    parse_individual_matches,
    parse_lineup,
    parse_standings,
    parse_team_matches,
    load_availability_data,
)


def camelize(value):
    if isinstance(value, dict):
        return {key[:1].lower() + key[1:]: camelize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [camelize(item) for item in value]
    return value


class RankedinParserTests(unittest.TestCase):
    def setUp(self):
        self.team_matches = {"Matches": [{
            "Team1": {"Id": 2701885, "Name": "Os", "Result": 4, "IsWinner": True},
            "Team2": {"Id": 2, "Name": "Dem", "Result": 2, "IsWinner": False},
            "MatchId": 137894,
            "Details": {"Round": 1, "Time": "01/05/2026 18:00", "LocationName": "Hallen"},
            "ShowResults": True,
        }]}
        side1 = {"Player1Id": 1, "Name": "Ada", "Player2Id": 2, "Player2Name": "Bo"}
        side2 = {"Player1Id": 3, "Name": "Carl", "Player2Id": 4, "Player2Name": "Dina"}
        score = {"FirstParticipantScore": 1, "SecondParticipantScore": 0,
                 "IsFirstParticipantWinner": True,
                 "DetailedScoring": [{"FirstParticipantScore": 6, "SecondParticipantScore": 4}]}
        self.details = [{"Matches": {"Matches": [{
            "Id": 99, "Date": "2026-05-01", "Challenger": side1, "Challenged": side2,
            "MatchResult": {"HasScore": True, "Score": score},
        }]}}]
        player = {"PlayerId": 1, "FirstName": "Ada", "LastName": "Andersen",
                  "PlayerRankedinId": 11, "HasLicense": True, "RatingBegin": 19.5,
                  "RankingTypePoints": [{"RankingType": 3, "Points": 42.0}],
                  "TeamParticipantType": 3}
        self.lineup = {"FirstTeam": {"Id": 2701885, "Players": [player]},
                       "SecondTeam": {"Id": 2, "Players": []}}
        self.standings = {"ScoresViewModels": [{
            "Standing": 1, "ParticipantId": 2701885, "ParticipantName": "Os",
            "MatchPoints": 12, "Played": 4, "Wins": 4, "Draws": 0, "Losses": 0,
            "GamesDifference": 8, "TeamGamesDifference": 20, "PointsDifference": 5,
        }]}

    def test_all_parsers_accept_pascal_case(self):
        self._assert_parsers(self.team_matches, self.details, self.lineup, self.standings)

    def test_all_parsers_accept_camel_case(self):
        self._assert_parsers(*(camelize(value) for value in
                               (self.team_matches, self.details, self.lineup, self.standings)))

    def test_missing_required_field_is_descriptive(self):
        with self.assertRaisesRegex(KeyError, "Matches.*matches.*Tilg.ngelige felter"):
            parse_team_matches({}, 2701885)

    def test_empty_lineup_is_a_valid_empty_dataframe(self):
        result = parse_lineup({"firstTeam": {"id": 2701885, "players": []},
                               "secondTeam": {"id": 2, "players": []}}, 2701885)
        self.assertTrue(result.empty)
        self.assertIn("ranking_pts", result.columns)

    @patch("padel_pipeline._load_availability_workbook")
    def test_old_availability_sheet_is_hidden_for_new_season(self, load_workbook):
        raw = pd.DataFrame("", index=range(20), columns=range(8))
        raw.iloc[7, 4] = "14/3"
        raw.iloc[8, 0] = "Spillere"
        raw.iloc[8, 4] = "kl. 12"
        raw.iloc[9, 4] = "PP-12"
        raw.iloc[10, 0] = "Rasmus B"
        raw.iloc[10, 4] = "x"
        load_workbook.return_value = raw
        season = pd.DataFrame({
            "datetime": [pd.Timestamp("2026-09-26 14:30")],
            "played": [False],
            "round": [1],
            "opponent": ["Outlaws Oldboys"],
            "venue": ["away"],
        })

        result = load_availability_data(season)

        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["matches"][0]["title"], "Runde 1 · 26/09/2026 14:30 · Outlaws Oldboys")
        self.assertEqual(result["matches"][0]["table"].iloc[0]["Kan spille"], "Ikke svaret")
        self.assertIn("ikke opdateret", result["reason"])

    def _assert_parsers(self, team_matches, details, lineup, standings):
        match = parse_team_matches(team_matches, 2701885).iloc[0]
        self.assertEqual((match["opponent"], match["our_score"], match["their_score"]), ("Dem", 4, 2))
        individual = parse_individual_matches(details, 137894, True)[0]
        self.assertEqual((individual["our_p1_name"], individual["sets_str"], individual["games_diff"]),
                         ("Ada", "6-4", 2))
        roster = parse_lineup(lineup, 2701885).iloc[0]
        self.assertEqual((roster["full_name"], roster["ranking_pts"], roster["role"]),
                         ("Ada Andersen", 42.0, "Captain"))
        standing = parse_standings(standings).iloc[0]
        self.assertEqual((standing["participant_id"], standing["match_points"], standing["games_diff"]),
                         (2701885, 12, 20))


if __name__ == "__main__":
    unittest.main()
