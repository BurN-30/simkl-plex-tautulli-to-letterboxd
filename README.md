# Simkl/Plex/Tautulli to Letterboxd

Export your watch history from Simkl, Plex, or Tautulli to a Letterboxd-compatible CSV with TMDB/IMDb validation.

![Screenshot](docs/screenshot.png)

## Features

- **Web Dashboard** - View, edit, and manage your movie collection
- **Real-time Sync** - Automatic background sync with Simkl (configurable interval)
- **Multiple Sources** - Simkl (primary), Plex and Tautulli (fallback)
- **TMDB Enrichment** - Automatic validation and retrieval of TMDB/IMDb IDs
- **Letterboxd Export** - CSV formatted for direct import
- **Statistics** - Ratings distribution, films per month/year

## Getting Started

This guide covers the default setup using **Simkl** as the data source. If you use Plex or Tautulli instead, follow steps 1–2, then jump to [Alternative Sources](#alternative-sources).

### 1. Install dependencies

**Windows:**

```powershell
git clone https://github.com/BurN-30/simkl-plex-tautulli-to-letterboxd.git
cd simkl-plex-tautulli-to-letterboxd
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

**Linux/macOS:**

```bash
git clone https://github.com/BurN-30/simkl-plex-tautulli-to-letterboxd.git
cd simkl-plex-tautulli-to-letterboxd
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Create your `.env` file

```powershell
copy .env.example .env    # Windows
cp .env.example .env      # Linux/macOS
```

Open `.env` in a text editor. You will fill in the required values in the next steps.

> **Important:** All placeholder values (`your_client_id`, `your_tmdb_api_key`, etc.) must be replaced with real values. The server will refuse to start if it detects a placeholder.

### 3. Register a Simkl app

You need to create an app on Simkl's developer portal to get the Client ID and Client Secret used for authentication.

1. Go to [https://simkl.com/settings/developer/](https://simkl.com/settings/developer/) and log in with your Simkl account
2. Click **Create new app**
3. Enter any name for the app (e.g. `Letterboxd Sync`)
4. Set the **Redirect URI** to exactly:
   ```
   http://localhost:19877/callback
   ```
   > This value must match exactly what the app expects. If you plan to change `OAUTH_PORT` in your `.env`, use that port number here instead of `19877`. A mismatch will cause Simkl to reject the connection.
5. Save the app
6. Copy the **Client ID** and the **Client Secret** from the app page, then paste them into `.env`:
   ```env
   SIMKL_CLIENT_ID=<your Client ID>
   SIMKL_CLIENT_SECRET=<your Client Secret>
   ```

### 4. Get a TMDB API key

TMDB is used to validate movie data and retrieve IMDb IDs, directors, and posters. A free account is sufficient.

1. Create an account at [https://www.themoviedb.org/](https://www.themoviedb.org/)
2. Go to **Settings → API** ([https://www.themoviedb.org/settings/api](https://www.themoviedb.org/settings/api))
3. Click **Create an application** and select **Personal**
4. Copy the **API Key (v3 auth)** and paste it into `.env`:
   ```env
   TMDB_API_KEY=<your TMDB API key>
   ```

### 5. Start the server

Make sure your virtual environment is activated, then run:

```bash
python src/server.py
```

Open [http://localhost:19876](http://localhost:19876) in your browser. If the server detects a missing or placeholder value in `.env`, it will print the exact error and refuse to start — fix the value and restart.

### 6. Connect your Simkl account

A banner at the top of the dashboard prompts you to authenticate with Simkl.

1. Click **Connect Simkl**
2. A new tab opens on Simkl's authorization page — log in and click **Allow**
3. Return to the dashboard. The banner disappears and the first sync starts automatically.

Your watched movies and watchlist are now imported. A new sync runs every 15 minutes in the background (configurable via `SYNC_INTERVAL` in `.env`).

---

### Alternative Sources

If you use **Plex** or **Tautulli** instead of Simkl, set `PRIMARY_SOURCE` in `.env` and fill in the corresponding values. You still need a valid `TMDB_API_KEY` regardless of the source.

**Plex:**

```env
PRIMARY_SOURCE=plex
PLEX_URL=http://your-plex-server:32400
PLEX_TOKEN=<your Plex token>
```

To find your Plex token: open Plex Web → Settings → Troubleshooting, or look for the `X-Plex-Token` header in any API call in browser DevTools.

**Tautulli:**

```env
PRIMARY_SOURCE=tautulli
TAUTULLI_URL=http://your-tautulli-server:8181
TAUTULLI_API_KEY=<your Tautulli API key>
TAUTULLI_USER_ID=1
```

`TAUTULLI_USER_ID` is the numeric ID of the user whose history you want to sync — check your Tautulli user list to find it.

---

### Docker

```bash
docker build -t simkl-to-letterboxd .
docker run --rm --env-file .env -p 19876:19876 -p 19877:19877 -v $(pwd)/output:/app/output simkl-to-letterboxd
```

> Both ports must be exposed: `19876` for the web dashboard and `19877` for the Simkl OAuth callback. The Redirect URI in your Simkl app must still point to `http://localhost:19877/callback`.

## CLI Export

The web dashboard is the recommended way to use the tool, but you can also run a one-off export from the command line:

```bash
python src/main.py
```

Options:
- `--source` - Data source override (simkl, plex, tautulli)
- `--no-watchlist` - Skip watchlist export
- `--no-watched` - Skip watched history export

## Output Files

| File | Description |
|------|-------------|
| `output/letterboxd_watched.csv` | Watched films with dates and ratings |
| `output/letterboxd_watchlist.csv` | Watchlist |
| `output/not_found.csv` | Films not found on TMDB |
| `logs/sync_YYYY-MM-DD.log` | Detailed logs |

## Letterboxd CSV Format

```csv
imdbID,tmdbID,Title,Year,Directors,WatchedDate,Rating,Rewatch,Tags,Review
tt0111161,278,The Shawshank Redemption,1994,Frank Darabont,2024-01-15,5,false,,
```

## Data Sources

| Source | Data | Available IDs |
|--------|------|---------------|
| Simkl | Watched, Ratings, Watchlist | TMDB, IMDb, TVDB |
| Plex | Watched, Ratings | TMDB, IMDb (via guids) |
| Tautulli | Watch history | Title + Year |

## Environment Variables

| Variable | Description | Default | Where to find it |
|----------|-------------|---------|------------------|
| `PRIMARY_SOURCE` | Which service to sync from (`simkl`, `plex`, `tautulli`) | `simkl` | — |
| `SIMKL_CLIENT_ID` | Your Simkl app client ID | — | [simkl.com/settings/developer](https://simkl.com/settings/developer/) |
| `SIMKL_CLIENT_SECRET` | Your Simkl app client secret | — | [simkl.com/settings/developer](https://simkl.com/settings/developer/) |
| `TMDB_API_KEY` | TMDB v3 API key | — | [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api) |
| `PLEX_URL` | URL of your Plex server | `http://localhost:32400` | Plex Web → Settings |
| `PLEX_TOKEN` | Plex authentication token | — | Plex Web → Settings → Troubleshooting (or `X-Plex-Token` header in DevTools) |
| `TAUTULLI_URL` | URL of your Tautulli instance | `http://localhost:8181` | Your Tautulli address bar |
| `TAUTULLI_API_KEY` | Tautulli API key | — | Tautulli → Settings → API |
| `TAUTULLI_USER_ID` | Numeric ID of the Tautulli user to sync | `1` | Tautulli → Users list |
| `WEB_PORT` | Web dashboard port | `19876` | — |
| `OAUTH_PORT` | Simkl OAuth callback port (must match redirect URI in Simkl app settings) | `19877` | — |
| `SYNC_INTERVAL` | Auto-sync interval in minutes | `15` | — |

## License

MIT
