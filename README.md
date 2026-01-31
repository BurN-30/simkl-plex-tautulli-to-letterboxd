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

1. Copy the example file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your API keys:
   - **SIMKL_CLIENT_ID** - Create an app at https://simkl.com/settings/developer/
   - **TMDB_API_KEY** - Get one at https://www.themoviedb.org/settings/api
   - **PLEX_TOKEN** (optional) - Plex authentication token
   - **TAUTULLI_API_KEY** (optional) - Tautulli API key

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

On first run, the tool automatically opens your browser for OAuth authentication. The token is saved to `.simkl_token`.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PRIMARY_SOURCE` | Data source | `simkl` |
| `SIMKL_CLIENT_ID` | Simkl app client ID | - |
| `TMDB_API_KEY` | TMDB API key | - |
| `PLEX_URL` | Plex server URL | `http://localhost:32400` |
| `PLEX_TOKEN` | Plex auth token | - |
| `TAUTULLI_URL` | Tautulli URL | `http://localhost:8181` |
| `TAUTULLI_API_KEY` | Tautulli API key | - |
| `WEB_PORT` | Web server port | `19876` |
| `SYNC_INTERVAL` | Auto-sync interval (minutes) | `15` |

## License

MIT
