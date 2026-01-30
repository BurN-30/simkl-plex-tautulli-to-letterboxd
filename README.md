# Letterboxd Sync Tool

A Python tool to export watch history (Simkl/Plex/Tautulli) to a Letterboxd-compatible CSV with TMDB/IMDB validation.

## Features

- **Multiple sources**: Simkl (primary), Plex and Tautulli (fallback)
- **TMDB enrichment**: Validation and retrieval of TMDB/IMDB IDs
- **Letterboxd CSV export**: Output formatted for direct import
- **Error handling**: Detailed logs and files for titles not found

## Installation

### Windows

```powershell
git clone <repo>
cd letterboxd-sync
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Linux/macOS

```bash
git clone <repo>
cd letterboxd-sync
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Docker

```bash
docker build -t letterboxd-sync .
docker run --rm --env-file .env -v $(pwd)/output:/app/output letterboxd-sync
```

## Configuration

1. Copy the example file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your API keys:
   - **SIMKL_CLIENT_ID**: Create an app at https://simkl.com/settings/developer/
   - **TMDB_API_KEY**: Obtain at https://www.themoviedb.org/settings/api
   - **PLEX_TOKEN** (optional): Plex authentication token
   - **TAUTULLI_API_KEY** (optional): Tautulli API key

## Usage

```bash
python src/main.py
```

### Options

- `--source`: Data source (simkl, plex, tautulli)
- `--no-watchlist`: Do not export the watchlist
- `--no-watched`: Do not export the watched history

## Generated files

| File | Description |
|------|-------------|
| `output/letterboxd_watched.csv` | Watched films with dates and ratings |
| `output/letterboxd_watchlist.csv` | Films to watch |
| `output/not_found.csv` | Titles not found on TMDB |
| `output/needs_review.csv` | Titles with ambiguous IDs |
| `logs/sync_YYYY-MM-DD.log` | Detailed logs |

## Letterboxd CSV Format

```csv
imdbID,tmdbID,Title,Year,Directors,WatchedDate,Rating,Rewatch,Tags,Review
tt0111161,278,The Shawshank Redemption,1994,Frank Darabont,2024-01-15,5,false,,
```

## Data sources

| Source | Data | IDs available |
|--------|------|---------------|
| Simkl | Watched, Ratings, Watchlist | TMDB, IMDB, TVDB |
| Plex | Watched, Ratings | TMDB, IMDB (via guids) |
| Tautulli | Watched history | Title + Year |

## Simkl authentication

On first run the tool will automatically open the browser for OAuth authentication. The token is saved to `.simkl_token`.

## License

MIT
