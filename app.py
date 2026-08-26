from github import Github
import json
import os
import pandas as pd
import streamlit as st

DATA_FILE = "darts_data.json"
GITHUB_REPO = "harrymddl/DDLELOTRACKER"


# --- 1. DATA STORAGE & GITHUB AUTO-SYNC ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"players": [], "matches": []}


def save_data(data):
    # Save locally to current session memory
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

    # Push directly to GitHub repository permanently
    if "GITHUB_TOKEN" in st.secrets:
        try:
            g = Github(st.secrets["GITHUB_TOKEN"])
            repo = g.get_repo(GITHUB_REPO)
            contents = repo.get_contents(DATA_FILE)
            repo.update_file(
                contents.path,
                "Auto-sync match result",
                json.dumps(data, indent=4),
                contents.sha,
            )
            st.success("✅ Match permanently saved to GitHub!")
        except Exception as e:
            st.error(f"❌ GitHub Sync Failed: {e}")
    else:
        st.warning(
            "⚠️ GITHUB_TOKEN not found in Streamlit Secrets! Match saved temporarily only."
        )


# --- 2. ELO ENGINE ---
def calculate_elo(r_a, r_b, outcome, k=32):
    e_a = 1 / (1 + 10 ** ((r_b - r_a) / 400))
    e_b = 1 - e_a
    new_r_a = r_a + k * (outcome - e_a)
    new_r_b = r_b + k * ((1 - outcome) - e_b)
    return new_r_a, new_r_b


def compute_all_ratings(data):
    all_time = {}
    seasons = {}
    player_stats = {}
    season_stats = {}

    for match in data["matches"]:
        p1 = match["player1"].strip().upper()
        p2 = match["player2"].strip().upper()
        winner = match["winner"].strip().upper()
        season = match.get("season", 1)

        for p in [p1, p2]:
            if p not in all_time:
                all_time[p] = 1500.0
            if p not in player_stats:
                player_stats[p] = {"played": 0, "wins": 0, "losses": 0}

        if season not in seasons:
            seasons[season] = {}
        if season not in season_stats:
            season_stats[season] = {}

        for p in [p1, p2]:
            if p not in seasons[season]:
                seasons[season][p] = 1500.0
            if p not in season_stats[season]:
                season_stats[season][p] = {"played": 0, "wins": 0, "losses": 0}

        player_stats[p1]["played"] += 1
        player_stats[p2]["played"] += 1
        season_stats[season][p1]["played"] += 1
        season_stats[season][p2]["played"] += 1

        if winner == p1:
            player_stats[p1]["wins"] += 1
            player_stats[p2]["losses"] += 1
            season_stats[season][p1]["wins"] += 1
            season_stats[season][p2]["losses"] += 1
        else:
            player_stats[p2]["wins"] += 1
            player_stats[p1]["losses"] += 1
            season_stats[season][p2]["wins"] += 1
            season_stats[season][p1]["losses"] += 1

        outcome_p1 = 1.0 if winner == p1 else 0.0

        all_time[p1], all_time[p2] = calculate_elo(
            all_time[p1], all_time[p2], outcome_p1
        )
        seasons[season][p1], seasons[season][p2] = calculate_elo(
            seasons[season][p1], seasons[season][p2], outcome_p1
        )

    return all_time, seasons, player_stats, season_stats


# --- 3. STREAMLIT APP UI ---
st.set_page_config(page_title="Darts League Elo Tracker", layout="wide")
st.title("DDL Elo Ratings")

data = load_data()
all_time_elo, season_elos, player_stats, season_stats = compute_all_ratings(data)

tab1, tab2, tab3 = st.tabs(
    ["📊 Leaderboards", "📝 Log Match", "⚙️ Manage Matches & Players"]
)

# TAB 1: LEADERBOARDS
with tab1:
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.header("League Leaderboards")
        available_views = ["All-Time Career"] + [
            f"Season {s}" for s in sorted(season_elos.keys(), reverse=True)
        ]
        selected_view = st.selectbox("Select Board View", options=available_views)

        if selected_view == "All-Time Career":
            records = []
            for p, elo in all_time_elo.items():
                stats = player_stats.get(
                    p, {"played": 0, "wins": 0, "losses": 0}
                )
                win_pct = (
                    f"{(stats['wins'] / stats['played'] * 100):.1f}%"
                    if stats["played"] > 0
                    else "0.0%"
                )
                records.append(
                    {
                        "Player": p,
                        "All-Time Elo": round(elo),
                        "Matches": stats["played"],
                        "W": stats["wins"],
                        "L": stats["losses"],
                        "Win %": win_pct,
                    }
                )
            df = pd.DataFrame(records)
            if not df.empty:
                df = df.sort_values(by="All-Time Elo", ascending=False)
        else:
            s_num = int(selected_view.split(" ")[1])
            records = []
            for p, elo in season_elos[s_num].items():
                stats = season_stats[s_num].get(
                    p, {"played": 0, "wins": 0, "losses": 0}
                )
                win_pct = (
                    f"{(stats['wins'] / stats['played'] * 100):.1f}%"
                    if stats["played"] > 0
                    else "0.0%"
                )
                records.append(
                    {
                        "Player": p,
                        f"Season {s_num} Elo": round(elo),
                        "Matches": stats["played"],
                        "W": stats["wins"],
                        "L": stats["losses"],
                        "Win %": win_pct,
                    }
                )
            df = pd.DataFrame(records)
            if not df.empty:
                df = df.sort_values(by=f"Season {s_num} Elo", ascending=False)

        if not df.empty:
            df.index = range(1, len(df) + 1)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No data available for this view.")

    with col_right:
        st.header("Player Inspector")
        all_known_players = sorted(list(all_time_elo.keys()))
        if all_known_players:
            inspect_p = st.selectbox("Select Player", options=all_known_players)
            st.metric("All-Time Elo", round(all_time_elo.get(inspect_p, 1500)))

            s_breakdown = {}
            for s_num, s_dict in season_elos.items():
                if inspect_p in s_dict:
                    s_breakdown[f"Season {s_num}"] = round(s_dict[inspect_p])

            st.write("**Seasonal Elo Ratings:**")
            st.json(s_breakdown)

# TAB 2: LOG MATCH REPORT
with tab2:
    st.header("Log a New Match Result")
    col1, col2, col3 = st.columns(3)

    with col1:
        season_input = st.number_input(
            "Season Number", min_value=1, value=4, step=1
        )
    with col2:
        p1 = st.text_input("Player 1 Name").strip().upper()
    with col3:
        p2 = st.text_input("Player 2 Name").strip().upper()

    if p1 and p2:
        winner = st.radio("Winner", [p1, p2], horizontal=True)

        if st.button("Submit Match Report"):
            if p1 == p2:
                st.error("Player 1 and Player 2 must be different!")
            else:
                new_match = {
                    "id": len(data["matches"]) + 1,
                    "season": int(season_input),
                    "player1": p1,
                    "player2": p2,
                    "winner": winner,
                }
                data["matches"].append(new_match)

                for p in [p1, p2]:
                    if p not in data["players"]:
                        data["players"].append(p)

                save_data(data)
                st.rerun()

# TAB 3: MANAGE MATCHES & PLAYERS
with tab3:
    st.header("Match History & Deletion")

    if data["matches"]:
        matches_df = pd.DataFrame(data["matches"])
        st.dataframe(matches_df, use_container_width=True)

        st.subheader("Delete an Incorrect Match")
        match_to_delete = st.number_input(
            "Enter Match ID to Delete",
            min_value=1,
            max_value=len(data["matches"]),
            step=1,
        )

        if st.button("Delete Selected Match"):
            data["matches"] = [
                m for m in data["matches"] if m["id"] != match_to_delete
            ]
            for idx, m in enumerate(data["matches"]):
                m["id"] = idx + 1
            save_data(data)
            st.warning(f"Deleted Match #{match_to_delete}. Ratings recalculated!")
            st.rerun()
    else:
        st.info("No matches logged yet.")

    st.markdown("---")
    st.header("✏️ Rename Player Records")

    existing_p = sorted(list(set(data["players"] + list(all_time_elo.keys()))))
    if existing_p:
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            old_name = st.selectbox("Select Current Player Name", options=existing_p)
        with col_r2:
            new_name = st.text_input("Enter New Name").strip().upper()

        if st.button("Rename Player Across All Matches"):
            if new_name and old_name:
                if old_name == new_name:
                    st.error("New name must be different from the old name!")
                else:
                    for m in data["matches"]:
                        if m["player1"] == old_name:
                            m["player1"] = new_name
                        if m["player2"] == old_name:
                            m["player2"] = new_name
                        if m["winner"] == old_name:
                            m["winner"] = new_name

                    data["players"] = [
                        new_name if p == old_name else p for p in data["players"]
                    ]
                    if new_name not in data["players"]:
                        data["players"].append(new_name)

                    save_data(data)
                    st.success(
                        f"Successfully renamed '{old_name}' to '{new_name}' across all records!"
                    )
                    st.rerun()
            else:
                st.error("Please enter a valid new name.")
