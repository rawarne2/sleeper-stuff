import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from datetime import date, datetime
import csv
import sys


def get_user_input():
    # Prompt for redraft league (boolean-like)
    while True:
        redraft_input = input(
            "Is your league a redraft league? Please enter 'True' or 'False': ").strip().lower()
        if redraft_input in ['true', 't', 'yes', 'y', '1']:
            is_redraft = True
            break
        elif redraft_input in ['false', 'f', 'no', 'n', '0']:
            is_redraft = False
            break
        else:
            print("Invalid input. Please enter 'True' or 'False'.")

    # Prompt for league format
    while True:
        format_input = input(
            "What is your league format? Please enter '1QB' or 'SF': ").strip().upper()
        if format_input in ['1QB', '1']:
            league_format = '1QB'
            break
        elif format_input in ['SF', 'SUPERFLEX', 'SUPER FLEX', 'S']:
            league_format = 'SF'
            break
        else:
            print("Invalid input. Please enter '1QB' or 'SF'.")

    # Prompt for TEP if not redraft
    tep = 0
    if not is_redraft:
        while True:
            tep_input = input(
                "Is there a Tight End Premium (TEP)? Please enter '0' for None, '1' for TE+, '2' for TE++, or '3' for TE+++: ").strip()
            if tep_input in ['0', '1', '2', '3']:
                tep = int(tep_input)
                break
            else:
                print("Invalid input. Please enter 0, 1, 2, or 3.")
    return is_redraft, league_format, tep


def fetch_ktc_page(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        print(f"HTTP error while fetching {url}: {e}")
        sys.exit(1)


def scrape_players(base_url, format_code, is_dynasty, value_key, pos_rank_key, max_pages=10):
    all_elements = []
    # Set progress bar description based on URL and format
    if 'dynasty' in base_url:
        if format_code == 1:
            desc = "Linking to keeptradecut.com's 1QB rankings..."
        else:
            desc = "Linking to keeptradecut.com's Superflex rankings..."
    else:
        if format_code == 1:
            desc = "Linking to keeptradecut.com's Redraft 1QB rankings..."
        else:
            desc = "Linking to keeptradecut.com's Redraft Superflex rankings..."
    for page_num in tqdm(range(max_pages), desc=desc, unit="page", mininterval=0.1):
        url = base_url.format(page_num, format_code)
        page = fetch_ktc_page(url)
        soup = BeautifulSoup(page.content, "html.parser")
        player_elements = soup.find_all(class_="onePlayer")
        all_elements.extend(player_elements)

    players = []
    for player_element in all_elements:
        player_name_element = player_element.find(class_="player-name")
        player_position_element = player_element.find(class_="position")
        player_value_element = player_element.find(class_="value")
        player_age_element = player_element.find(class_="position hidden-xs")

        if not (player_name_element and player_position_element and player_value_element):
            continue

        player_name = player_name_element.get_text(strip=True)
        team_suffix = (
            player_name[-3:] if player_name[-3:] == 'RFA' else
            player_name[-4:] if len(player_name) >= 4 and player_name[-4] == 'R' else
            player_name[-2:] if player_name[-2:] == 'FA' else
            player_name[-3:] if player_name[-3:].isupper() else ""
        )
        player_name = player_name.replace(team_suffix, "").strip()
        player_position_rank = player_position_element.get_text(strip=True)
        player_position = player_position_rank[:2]
        try:
            player_value = int(player_value_element.get_text(strip=True))
        except Exception:
            player_value = 0
        player_age = None
        if is_dynasty and player_age_element:
            player_age_text = player_age_element.get_text(strip=True)
            try:
                player_age = float(
                    player_age_text[:4]) if player_age_text else None
            except Exception:
                player_age = None
        else:
            player_age = None
        if team_suffix and team_suffix[0] == 'R':
            player_team = team_suffix[1:]
            player_rookie = "Yes"
        else:
            player_team = team_suffix
            player_rookie = "No"
        if player_position == "PI":
            player_info = {
                "Player Name": player_name,
                pos_rank_key: None,
                "Position": player_position,
                "Team": None,
                value_key: player_value,
                "Age": player_age if is_dynasty else None,
                "Rookie": player_rookie if is_dynasty else None
            }
        else:
            player_info = {
                "Player Name": player_name,
                pos_rank_key: player_position_rank,
                "Position": player_position,
                "Team": player_team,
                value_key: player_value,
                "Age": player_age if is_dynasty else None,
                "Rookie": player_rookie if is_dynasty else None
            }
        players.append(player_info)
    return players


def merge_redraft_values(players, base_url, format_code, value_key, pos_rank_key, max_pages=10):
    all_elements = []
    for page_num in tqdm(range(max_pages), desc=f"Scraping {base_url} format={format_code}...", unit="page"):
        url = base_url.format(page_num, format_code)
        page = fetch_ktc_page(url)
        soup = BeautifulSoup(page.content, "html.parser")
        player_elements = soup.find_all(class_="onePlayer")
        all_elements.extend(player_elements)
    for player_element in all_elements:
        player_name_element = player_element.find(class_="player-name")
        player_position_element = player_element.find(class_="position")
        player_value_element = player_element.find(class_="value")
        if not (player_name_element and player_position_element and player_value_element):
            continue
        player_name = player_name_element.get_text(strip=True)
        team_suffix = (
            player_name[-3:] if player_name[-3:] == 'RFA' else
            player_name[-4:] if len(player_name) >= 4 and player_name[-4] == 'R' else
            player_name[-2:] if player_name[-2:] == 'FA' else
            player_name[-3:] if player_name[-3:].isupper() else ""
        )
        player_name = player_name.replace(team_suffix, "").strip()
        player_position_rank = player_position_element.get_text(strip=True)
        try:
            player_value = int(player_value_element.get_text(strip=True))
        except Exception:
            player_value = 0
        for player in players:
            if player["Player Name"] == player_name:
                player[pos_rank_key] = player_position_rank
                player[value_key] = player_value
                break
    return players


def scrape_ktc(is_redraft, league_format):
    # Only scrape the format the user selected
    if league_format == '1QB':
        format_code = 1
        value_key = 'Value'
        pos_rank_key = 'Position Rank'
        base_url = "https://keeptradecut.com/dynasty-rankings?page={0}&filters=QB|WR|RB|TE|RDP&format={1}"
        players = scrape_players(
            base_url, format_code, True, value_key, pos_rank_key)
        if is_redraft:
            redraft_url = "https://keeptradecut.com/fantasy-rankings?page={0}&filters=QB|WR|RB|TE&format={1}"
            players = merge_redraft_values(
                players, redraft_url, 1, 'RdrftValue', 'RdrftPosition Rank')
    else:  # SF
        format_code = 0
        value_key = 'SFValue'
        pos_rank_key = 'SFPosition Rank'
        base_url = "https://keeptradecut.com/dynasty-rankings?page={0}&filters=QB|WR|RB|TE|RDP&format={1}"
        players = scrape_players(
            base_url, format_code, True, value_key, pos_rank_key)
        if is_redraft:
            redraft_url = "https://keeptradecut.com/fantasy-rankings?page={0}&filters=QB|WR|RB|TE&format={1}"
            players = merge_redraft_values(
                players, redraft_url, 2, 'SFRdrftValue', 'SFRdrftPosition Rank')
    return players


def tep_adjust(rows_data, tep, value_col_names):
    header = rows_data[0]
    col_indices = {col: header.index(col)
                   for col in value_col_names if col in header}
    # Sort by the first value column for consistency
    first_val_col = value_col_names[0] if value_col_names else None
    if first_val_col and first_val_col in header:
        rows_data = [
            header] + sorted(rows_data[1:], key=lambda x: x[header.index(first_val_col)], reverse=True)
    if tep == 0:
        return rows_data
    s = 0.2
    if tep == 1:
        t_mult = 1.1
        r = 250
    elif tep == 2:
        t_mult = 1.2
        r = 350
    elif tep == 3:
        t_mult = 1.3
        r = 450
    else:
        print(f"Error: invalid TEP value -- {tep}")
        sys.exit(1)
    for col, idx in col_indices.items():
        rank = 0
        max_player_val = rows_data[1][idx]
        for player in rows_data[1:]:
            if player[header.index("Position")] == "TE":
                t = t_mult * player[idx]
                n = rank / (len(rows_data) - 25) * r + s * r
                player[idx] = min(max_player_val - 1, round(t + n, 2))
            rank += 1
    # Re-sort
    if first_val_col and first_val_col in header:
        rows_data = [
            header] + sorted(rows_data[1:], key=lambda x: x[header.index(first_val_col)], reverse=True)
    return rows_data


def make_unique(rows_data, value_col_names):
    header = rows_data[0]
    col_indices = [header.index(col)
                   for col in value_col_names if col in header]
    for idx in col_indices:
        seen_values = set()
        for player in rows_data[1:]:
            current_value = player[idx]
            while current_value in seen_values:
                current_value -= 0.01
            seen_values.add(current_value)
            player[idx] = current_value
    return rows_data


def export_to_csv(players, league_format, tep, is_redraft):
    timestamp = f"Updated {date.today().strftime('%m/%d/%y')} at {datetime.now().strftime('%I:%M%p').lower()}"
    if is_redraft:
        if league_format == '1QB':
            header = [timestamp, "Position Rank",
                      "Position", "Team", "RdrftValue"]
            value_cols = ["RdrftValue"]
            rows_data = [
                [player["Player Name"], player.get(
                    "RdrftPosition Rank"), player["Position"], player["Team"], player.get("RdrftValue", 0)]
                for player in players if player.get("RdrftValue", 0) > 0
            ]
        else:
            header = [timestamp, "SFPosition Rank",
                      "Position", "Team", "SFRdrftValue"]
            value_cols = ["SFRdrftValue"]
            rows_data = [
                [player["Player Name"], player.get(
                    "SFRdrftPosition Rank"), player["Position"], player["Team"], player.get("SFRdrftValue", 0)]
                for player in players if player.get("SFRdrftValue", 0) > 0
            ]
    else:
        if league_format == '1QB':
            header = [timestamp, "Position Rank",
                      "Position", "Team", "Value", "Age", "Rookie"]
            value_cols = ["Value"]
            rows_data = [
                [player["Player Name"], player.get("Position Rank"), player["Position"], player["Team"], player.get(
                    "Value", 0), player.get("Age"), player.get("Rookie")]
                for player in players if player.get("Value", 0) > 0
            ]
        else:
            header = [timestamp, "SFPosition Rank",
                      "Position", "Team", "SFValue", "Age", "Rookie"]
            value_cols = ["SFValue"]
            rows_data = [
                [player["Player Name"], player.get("SFPosition Rank"), player["Position"], player["Team"], player.get(
                    "SFValue", 0), player.get("Age"), player.get("Rookie")]
                for player in players if player.get("SFValue", 0) > 0
            ]
    rows_data.insert(0, header)
    if not is_redraft and tep > 0:
        rows_data = tep_adjust(rows_data, tep, value_cols)
    rows_data = make_unique(rows_data, value_cols)
    csv_filename = 'ktc.csv'
    with open(csv_filename, 'w', newline='') as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerows(rows_data)
    print(
        f"Data exported to {csv_filename} on {date.today().strftime('%B %d, %Y')} successful.")


if __name__ == "__main__":
    is_redraft, league_format, tep = get_user_input()
    players = scrape_ktc(is_redraft, league_format)
    export_to_csv(players, league_format, tep, is_redraft)
