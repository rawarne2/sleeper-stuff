import requests
import os
from bs4 import BeautifulSoup
from tqdm import tqdm
from datetime import date, datetime
import csv
import sys
import boto3
from botocore.exceptions import NoCredentialsError, ClientError


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

    # Prompt for S3 upload - simplified to just yes/no
    while True:
        s3_upload_input = input(
            "Do you want to upload the CSV to S3? (yes/no): ").strip().lower()
        if s3_upload_input in ['yes', 'y', '1', 'true', 't']:
            s3_upload = True
            break
        elif s3_upload_input in ['no', 'n', '0', 'false', 'f']:
            s3_upload = False
            break
        else:
            print("Invalid input. Please enter 'yes' or 'no'.")

    s3_bucket = os.getenv('S3_BUCKET')
    s3_key = "ktc.csv"

    return is_redraft, league_format, tep, s3_upload, s3_bucket, s3_key


def fetch_ktc_page(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        print(f"HTTP error while fetching {url}: {e}")
        sys.exit(1)


def scrape_players(base_url, format_code, value_key, pos_rank_key, max_pages=10):
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

        # Extract rank number
        rank_element = player_element.find(class_="rank-number")
        try:
            player_rank = int(rank_element.get_text(
                strip=True)) if rank_element else None
        except (ValueError, AttributeError):
            player_rank = None

        # Extract trend with direction
        trend_element = player_element.find(class_="trend")
        player_trend = None
        if trend_element:
            trend_value = trend_element.get_text(strip=True)
            if trend_element.contents and len(trend_element.contents) > 1:
                try:
                    trend_class = trend_element.contents[1].attrs.get("class", [""])[
                        0]
                    if trend_class == "trend-up":
                        player_trend = f"+{trend_value}" if trend_value else "+0"
                    elif trend_class == "trend-down":
                        player_trend = f"-{trend_value}" if trend_value else "-0"
                    else:
                        player_trend = "0"
                except (IndexError, AttributeError):
                    player_trend = "0"
            else:
                player_trend = "0"
        else:
            player_trend = "0"

        # Extract tier
        player_tier = None
        player_info_element = player_element.find(class_="player-info")
        if player_info_element and len(player_info_element.contents) > 1:
            try:
                player_tier = player_info_element.contents[1].get_text(
                    strip=True)
            except (IndexError, AttributeError):
                player_tier = None

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

        # Always extract age regardless of league type
        player_age = None
        if player_age_element:
            player_age_text = player_age_element.get_text(strip=True)
            try:
                player_age = float(
                    player_age_text[:4]) if player_age_text else None
            except Exception:
                player_age = None

        # Always determine rookie status
        if team_suffix and team_suffix[0] == 'R':
            player_team = team_suffix[1:]
            player_rookie = "Yes"
        else:
            player_team = team_suffix
            player_rookie = "No"

        if player_position == "PI":  # Player Inactive
            player_info = {
                "Player Name": player_name,
                pos_rank_key: None,
                "Position": player_position,
                "Team": None,
                value_key: player_value,
                "Age": player_age,
                "Rookie": player_rookie,
                "Rank": player_rank,
                "Trend": player_trend,
                "Tier": player_tier
            }
        else:
            player_info = {
                "Player Name": player_name,
                pos_rank_key: player_position_rank,
                "Position": player_position,
                "Team": player_team,
                value_key: player_value,
                "Age": player_age,
                "Rookie": player_rookie,
                "Rank": player_rank,
                "Trend": player_trend,
                "Tier": player_tier
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

        # Extract rank number
        rank_element = player_element.find(class_="rank-number")
        try:
            redraft_rank = int(rank_element.get_text(
                strip=True)) if rank_element else None
        except (ValueError, AttributeError):
            redraft_rank = None

        # Extract trend with direction
        trend_element = player_element.find(class_="trend")
        redraft_trend = None
        if trend_element:
            trend_value = trend_element.get_text(strip=True)
            if trend_element.contents and len(trend_element.contents) > 1:
                try:
                    trend_class = trend_element.contents[1].attrs.get("class", [""])[
                        0]
                    if trend_class == "trend-up":
                        redraft_trend = f"+{trend_value}" if trend_value else "+0"
                    elif trend_class == "trend-down":
                        redraft_trend = f"-{trend_value}" if trend_value else "-0"
                    else:
                        redraft_trend = "0"
                except (IndexError, AttributeError):
                    redraft_trend = "0"
            else:
                redraft_trend = "0"
        else:
            redraft_trend = "0"

        # Extract tier
        redraft_tier = None
        player_info_element = player_element.find(class_="player-info")
        if player_info_element and len(player_info_element.contents) > 1:
            try:
                redraft_tier = player_info_element.contents[1].get_text(
                    strip=True)
            except (IndexError, AttributeError):
                redraft_tier = None

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
                player["RdrftRank"] = redraft_rank
                player["RdrftTrend"] = redraft_trend
                player["RdrftTier"] = redraft_tier
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
            base_url, format_code, value_key, pos_rank_key)
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
            base_url, format_code, value_key, pos_rank_key)
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


def upload_to_s3(file_path, bucket_name, object_key):
    """
    Upload a file to an S3 bucket

    Parameters:
    file_path (str): The path to the file to upload
    bucket_name (str): The name of the S3 bucket
    object_key (str): The S3 object key (path/filename.csv)

    Returns:
    bool: True if upload was successful, False otherwise
    """
    try:
        s3_client = boto3.client('s3')
        print(f"Uploading {file_path} to s3://{bucket_name}/{object_key}...")
        s3_client.upload_file(file_path, bucket_name, object_key)
        print(
            f"Successfully uploaded {file_path} to s3://{bucket_name}/{object_key}")
        return True
    except NoCredentialsError:
        print("Error: AWS credentials not found. Make sure you've configured your AWS credentials.")
        return False
    except ClientError as e:
        print(f"Error uploading to S3: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error uploading to S3: {e}")
        return False


def export_to_csv(players, league_format, tep, is_redraft, s3_upload=False, s3_bucket=None, s3_key=None):
    timestamp = f"Updated {date.today().strftime('%m/%d/%y')} at {datetime.now().strftime('%I:%M%p').lower()}"
    if is_redraft:
        if league_format == '1QB':
            header = [timestamp, "Rank", "Trend", "Tier",
                      "Position Rank", "Position", "Team", "RdrftValue", "Age", "Rookie"]
            value_cols = ["RdrftValue"]
            rows_data = [
                [player["Player Name"], player.get("RdrftRank"), player.get("RdrftTrend", "0"), player.get("RdrftTier"),
                 player.get(
                     "RdrftPosition Rank"), player["Position"], player["Team"],
                 player.get("RdrftValue", 0), player.get("Age"), player.get("Rookie")]
                for player in players if player.get("RdrftValue", 0) > 0
            ]
        else:
            header = [timestamp, "Rank", "Trend", "Tier",
                      "Position Rank", "Position", "Team", "SFRdrftValue", "Age", "Rookie"]
            value_cols = ["SFRdrftValue"]
            rows_data = [
                [player["Player Name"], player.get("RdrftRank"), player.get("RdrftTrend", "0"), player.get("RdrftTier"),
                 player.get(
                     "SFRdrftPosition Rank"), player["Position"], player["Team"],
                 player.get("SFRdrftValue", 0), player.get("Age"), player.get("Rookie")]
                for player in players if player.get("SFRdrftValue", 0) > 0
            ]
    else:
        if league_format == '1QB':
            header = [timestamp, "Rank", "Trend", "Tier",
                      "Position Rank", "Position", "Team", "Value", "Age", "Rookie"]
            value_cols = ["Value"]
            rows_data = [
                [player["Player Name"], player.get("Rank"), player.get("Trend", "0"), player.get("Tier"),
                 player.get(
                     "Position Rank"), player["Position"], player["Team"],
                 player.get("Value", 0), player.get("Age"), player.get("Rookie")]
                for player in players if player.get("Value", 0) > 0
            ]
        else:
            header = [timestamp, "Rank", "Trend", "Tier",
                      "Position Rank", "Position", "Team", "SFValue", "Age", "Rookie"]
            value_cols = ["SFValue"]
            rows_data = [
                [player["Player Name"], player.get("Rank"), player.get("Trend", "0"), player.get("Tier"),
                 player.get(
                     "SFPosition Rank"), player["Position"], player["Team"],
                 player.get("SFValue", 0), player.get("Age"), player.get("Rookie")]
                for player in players if player.get("SFValue", 0) > 0
            ]
    rows_data.insert(0, header)
    if not is_redraft and tep > 0:
        rows_data = tep_adjust(rows_data, tep, value_cols)

    # Remove call to make_unique and instead sort by value and then by rank
    # If two players have the same value, the one with better rank (lower number) will come first
    value_col = value_cols[0]
    value_idx = header.index(value_col)
    rank_idx = header.index("Rank")

    # Sort first by value (descending), then by rank (ascending) when values are equal
    rows_data = [header] + sorted(rows_data[1:],
                                  key=lambda x: (
                                      x[value_idx], -float(x[rank_idx]) if x[rank_idx] is not None else float('inf')),
                                  reverse=True)

    csv_filename = 'ktc.csv'
    with open(csv_filename, 'w', newline='') as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerows(rows_data)
    print(
        f"Data exported to {csv_filename} on {date.today().strftime('%B %d, %Y')} successful.")

    # Upload to S3 if requested
    if s3_upload and s3_bucket and s3_key:
        upload_to_s3(csv_filename, s3_bucket, s3_key)


if __name__ == "__main__":
    is_redraft, league_format, tep, s3_upload, s3_bucket, s3_key = get_user_input()
    players = scrape_ktc(is_redraft, league_format)
    export_to_csv(players, league_format, tep, is_redraft,
                  s3_upload, s3_bucket, s3_key)
