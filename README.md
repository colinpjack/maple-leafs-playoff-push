# The Push — Maple Leafs playoff dashboard

A GitHub Pages site that tracks the Toronto Maple Leafs' playoff chase. Hockey does not use a wins-and-losses wild-card table, so the board is built around the things that actually decide April:

- **Points** — a win is 2, an overtime or shootout loss is 1
- **Two routes in** — top three in the Atlantic, or one of two Eastern wild cards
- **Tiebreakers** — regulation wins, then regulation-plus-overtime wins
- **The schedule** — games left, back-to-backs, and a simulated playoff probability

Before opening night the standings are still last season's. The page says so, shows that finish, and runs the new schedule through the model. Once regular-season games count, the same page switches to the live race.

## Enable it on GitHub

1. Create a GitHub repo and push this project (default branch `main` or `master`).
2. In the repo: **Settings → Pages → Build and deployment**
   - Source: **Deploy from a branch**
   - Branch: `main` (or `master`), folder: `/ (root)`
3. In **Settings → Actions → General**, allow GitHub Actions and permit the workflow to read and write contents so it can commit `data.json`.
4. Open **Actions → Update playoff dashboard → Run workflow** once so the first refresh is confirmed.

The public URL will be:

`https://<your-github-username>.github.io/<repo-name>/`

## What updates

A scheduled GitHub Action runs `scripts/fetch_playoff_data.py`, which writes `data.json` from the [NHL API](https://api-web.nhle.com/). If nothing in the race changed, the workflow skips the commit.

## Local refresh

```bash
python3 scripts/fetch_playoff_data.py
python3 -m http.server 8080
```

Visit [http://localhost:8080](http://localhost:8080). Opening `index.html` as a file will block `fetch`.

## Notes

This is a fan dashboard, not an official NHL or Maple Leafs product. The playoff percentage is a season simulation from points percentage and home ice. It is not a betting line.
