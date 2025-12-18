with open('extract_leaderboard_out.txt', 'w', encoding='utf-8') as out:
    try:
        with open('backtest_unfiltered_results.txt', 'r', encoding='utf-16', errors='ignore') as f:
            content = f.read()
            if "Final Leaderboard" in content:
                start = content.find("Final Leaderboard")
                out.write(content[start:])
            else:
                out.write("Leaderboard not found in file.")
    except Exception as e:
        out.write(f"Error: {e}")
