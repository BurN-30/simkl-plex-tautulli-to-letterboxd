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

## Installation

### Windows

```powershell
git clone https://github.com/BurN-30/simkl-plex-tautulli-to-letterboxd.git
cd simkl-plex-tautulli-to-letterboxd
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Linux/macOS

```bash
git clone https://github.com/BurN-30/simkl-plex-tautulli-to-letterboxd.git
cd simkl-plex-tautulli-to-letterboxd
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Docker

```bash
docker build -t simkl-to-letterboxd .
docker run --rm --env-file .env -p 19876:19876 -v $(pwd)/output:/app/output simkl-to-letterboxd
```

## Configuration

### 1. Copy the example file

```bash
cp .env.example .env
```

> **Important:** All placeholder values (`your_client_id`, `your_tmdb_api_key`, etc.) must be replaced with real values. The server will refuse to start if it detects a placeholder.

### 2. Simkl Client ID (required if `PRIMARY_SOURCE=simkl`)

1. Go to [https://simkl.com/settings/developer/](https://simkl.com/settings/developer/)
2. Log in with your Simkl account
3. Click **Create new app**
4. Fill in the name and set the **Redirect URI** to:
   ```
   http://localhost:19877/callback
   ```
   > If you changed `OAUTH_PORT` in `.env`, use that port number instead of `19877`.
5. Copy the **Client ID** and the **Client Secret** and paste them into `.env`:
   ```
   SIMKL_CLIENT_ID=your_actual_client_id_here
   SIMKL_CLIENT_SECRET=your_actual_client_secret_here
   ```

### 3. TMDB API Key (required)

1. Create a free account at [https://www.themoviedb.org/](https://www.themoviedb.org/)
2. Go to **Settings → API** (https://www.themoviedb.org/settings/api)
3. Create an application (select **Personal** use)
4. Copy the **API Key (v3 auth)** and paste it into `.env`:
   ```
   TMDB_API_KEY=your_actual_tmdb_key_here
   ```

### 4. Plex Token (only if `PRIMARY_SOURCE=plex`)

1. Open **Plex Web** and log in
2. Go to **Settings → Troubleshooting**
3. Click **Copy Support Logs** — your token is visible in the URL bar when accessing your Plex server, or you can extract it from any API call in the browser DevTools (look for the `X-Plex-Token` header)
4. Paste it into `.env`:
   ```
   PLEX_TOKEN=your_actual_plex_token_here
   PLEX_URL=http://your-plex-server:32400
   ```

### 5. Tautulli API Key (only if `PRIMARY_SOURCE=tautulli`)

1. Open your **Tautulli** web interface
2. Go to **Settings → API** (usually at `/settings`)
3. Copy the **API Key** and paste it into `.env`:
   ```
   TAUTULLI_API_KEY=your_actual_tautulli_key_here
   TAUTULLI_URL=http://your-tautulli-server:8181
   TAUTULLI_USER_ID=1
   ```
   > `TAUTULLI_USER_ID` is the numeric ID of the user whose history you want to sync. Check Tautulli's user list to find it.

## Usage

### Web Interface (Recommended)

```bash
python src/server.py
```

Open http://localhost:19876 in your browser.

Features:
- View all watched films with posters, ratings, and dates
- Edit ratings, watch dates, tags, and reviews
- Filter by year, rating, or search by title
- View statistics and charts
- Auto-sync with Simkl every 15 minutes (configurable)
- Export to Letterboxd CSV

### CLI Export

```bash
python src/main.py
```

Options:
- `--source` - Data source (simkl, plex, tautulli)
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

## Simkl Authentication

On first launch, a banner appears at the top of the dashboard with a **Connecter Simkl** button. Clicking it opens the Simkl authorization page in a new tab. After you grant access, the token is saved automatically to `.simkl_token` and syncing starts.

> The **Redirect URI** configured in your Simkl app must match `http://localhost:{OAUTH_PORT}/callback` (default: `http://localhost:19877/callback`). If they don't match, Simkl will reject the request.

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
