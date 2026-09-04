# Simkl/Plex/Tautulli to Letterboxd

Turn your watch history, ratings and reviews into Letterboxd import files.

The tool keeps a local database of everything you have watched, remembers which
entries you have already imported, and writes CSV files in the exact format the
Letterboxd importer expects. You upload those files yourself at
[letterboxd.com/import](https://letterboxd.com/import). Nothing is ever pushed
to Letterboxd automatically.

## How it works

```
  Simkl (or Plex / Tautulli)
            |
            |  sync
            v
      SQLite database  <-----  reviews, tags and rewatch flags typed
            |                   in the web dashboard
            |  export --incremental
            v
     output/pending/*.csv
            |
            |  you upload them at letterboxd.com/import
            v
        Letterboxd
            |
            |  confirm
            v
   export state updated, files moved to output/done/
```

The Letterboxd importer updates an existing diary entry when a line's film and
`WatchedDate` match one already in your diary, so re-importing the same data
never creates duplicates. That property is what makes a recurring CSV workflow
viable, and it is what the export state is built around: an entry is identified
by the pair (film, `WatchedDate`), and re-exported only when its rating, review,
tags or rewatch flag changed since you last confirmed an import.

## Features

- **Simkl as primary source** - completed films, ratings and watchlist, with
  Plex and Tautulli kept as secondary sources
- **Incremental exports** - only what is new or edited since the last confirmed
  import, so a weekly upload takes seconds
- **Correct CSV dialect** - Letterboxd escapes quotes with a backslash, not by
  doubling them; files are UTF-8 without BOM, LF endings, split under the 1 MB
  limit with the header repeated in every part
- **Calendar dates, not timestamps** - Plex and Tautulli timestamps are
  converted from UTC to your local zone before being truncated to a date
- **Optional TMDB enrichment** - works fine without a TMDB key, relying on the
  TMDB and IMDb ids the source already provides
- **Web dashboard** - browse the collection, write reviews, set tags, mark
  rewatches, see the statistics
- **Weekly Windows scheduled task** - `sync` then `export --incremental`

## Getting started

### 1. Install

```powershell
git clone https://github.com/BurN-30/simkl-plex-tautulli-to-letterboxd.git
cd simkl-plex-tautulli-to-letterboxd
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

On Linux or macOS, use `python3 -m venv venv` and `source venv/bin/activate`.

### 2. Configure

```powershell
copy .env.example .env    # Windows
cp .env.example .env      # Linux/macOS
```

Fill in `SIMKL_CLIENT_ID` and `SIMKL_CLIENT_SECRET`. Everything else has a
usable default, and `TMDB_API_KEY` can stay empty.

### 3. Register a Simkl app

1. Go to [simkl.com/settings/developer](https://simkl.com/settings/developer/)
2. **Create new app**, any name
3. Redirect URI, exactly: `http://localhost:19877/callback` (use your
   `OAUTH_PORT` if you changed it, a mismatch makes Simkl reject the connection)
4. Copy the Client ID and Client Secret into `.env`

### 4. Authorise

```powershell
python -m src.cli serve
```

Open [http://localhost:19876](http://localhost:19876), click **Connect Simkl**,
approve in the tab that opens. The access token is written to
`data/simkl_token.json` (path configurable with `SIMKL_TOKEN_FILE`).

If you already have a Simkl access token, write it there yourself:

```json
{ "access_token": "..." }
```

### 5. First run

```powershell
python -m src.cli sync
python -m src.cli export --full
```

Upload `output\pending\letterboxd_watched_*.csv` at
[letterboxd.com/import](https://letterboxd.com/import), check the preview
screen, confirm, then:

```powershell
python -m src.cli confirm output\pending\letterboxd_watched_20260904-120333.csv
```

From then on, `export --incremental` only writes what changed.

## Commands

| Command | What it does |
|---|---|
| `python -m src.cli sync` | Pull the source into the local database |
| `python -m src.cli export` | Write only new or changed entries (incremental, the default) |
| `python -m src.cli export --full` | Write every entry, ignoring the export state |
| `python -m src.cli export --no-watchlist` | Skip the watchlist file |
| `python -m src.cli confirm <file.csv>` | Mark that file's rows as imported and archive it |
| `python -m src.cli confirm <file.csv> --keep` | Same, without moving the file |
| `python -m src.cli status` | Counters: total, pending, last sync, last confirmed import |
| `python -m src.cli serve` | Web dashboard on `WEB_PORT` |

`confirm` reads the CSV back with the same parser that wrote it, so what gets
marked as imported is exactly what Letterboxd received. Run it only after the
import actually completed, otherwise those entries will be considered done and
skipped by the next incremental export (use `export --full` to recover).

## Weekly routine

1. The scheduled task runs `sync`, then `export --incremental`
2. Any new or edited entry lands as a CSV in `output\pending\`
3. You upload it at [letterboxd.com/import](https://letterboxd.com/import) and
   confirm on the preview screen
4. You run `confirm` on the file, which archives it under `output\done\`

Nothing happens when nothing changed: no file is written and there is nothing
to upload.

### Installing the scheduled task (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1
```

Registers `LetterboxdSync-Weekly`, running Sunday at 09:00 local time under
your account, logging to `logs\weekly-task.log`. Options:

```powershell
scripts\install-task.ps1 -At 21:30 -DayOfWeek Monday
scripts\install-task.ps1 -Python C:\path\to\python.exe
scripts\uninstall-task.ps1
```

`scripts\run-weekly.ps1` is the job itself, and can be run by hand:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-weekly.ps1
```

## Reviews and tags

No source provides review text, so reviews are written in the dashboard: click
a film, fill in the review, tags, rating or rewatch flag, save. A sync never
overwrites those fields.

Editing any of them makes the entry pending again, and the next incremental
export includes it. Because the importer matches on (film, `WatchedDate`),
re-importing updates the existing diary entry rather than adding a second one.

Reviews accept the same HTML subset as the Letterboxd website (`<br>`,
`<strong>`, `<em>`, `<b>`, `<i>`, `<a href="">`, `<blockquote>`).

## CSV format

Watched films:

```csv
tmdbID,imdbID,Title,Year,Directors,WatchedDate,Rating10,Rewatch,Tags,Review
11,tt0076759,Star Wars,1977,,2023-06-18,10,false,,
103,tt0075314,"Taxi Driver",1976,,2024-02-11,9,false,"crime, rewatch","He said \"you talkin' to me\"."
```

Watchlist:

```csv
Title,Year,tmdbID,imdbID
1917,2019,530915,tt8579674
```

Details that matter, all from
[letterboxd.com/about/importing-data](https://letterboxd.com/about/importing-data/):

- **Quote escaping uses a backslash.** Letterboxd asks you to "escape quotes
  within quoted text, by prefixing them with a backslash (`\`) character". This
  is not RFC 4180, and Python's `csv` module cannot produce it: it doubles the
  quote instead, which Letterboxd reads as two literal quotes. The dialect is
  implemented in `src/letterboxd/csv_format.py` and covered by tests. Literal
  backslashes are escaped as `\\` so that the writer and the reader stay exactly
  reversible.
- **Only one rating column.** "If both Rating columns contain data on any given
  line of the file, whichever column appears second in the file will take
  precedence." Only `Rating10` (1-10) is emitted, never `Rating` (0.5-5).
- **1 MB per file.** Files are split below that threshold
  (`MAX_CSV_BYTES`, default 950000) with the header repeated in every part, and
  numbered `_part01`, `_part02`, and so on. Long reviews are what makes this
  limit bite, not the number of films.
- **Calendar dates, no timestamps.** Letterboxd asks for the date "after
  performing any necessary time-zone conversion, such as from UTC to your local
  time zone". Plex and Tautulli timestamps are converted to `LOCAL_TIMEZONE`
  first. Simkl dates are kept as they come by default, because most of them are
  midnight markers left by a bulk import rather than real watch times; set
  `SIMKL_CONVERT_TIMEZONE=true` to convert the ones that do carry a time.
- **No space after the comma**, ever, as it "can interfere with the parsing of
  quoted strings".
- **Two lines for the same film on the same date merge into one entry.** Real
  separate viewings on the same day have to be added by hand.

## Why not automate the upload

Letterboxd's API is complete enough to do all of this in one call, but access is
granted by request only, and the
[api-beta page](https://letterboxd.com/api-beta/) rules this use case out:

> At this time we are not granting access for data-analysis, visualization or
> recommendation projects, for LLM or GPT-related use, for **private or personal
> projects**, or for any usage that recreates current or planned features of our
> paid subscription tiers.

The same page points personal use towards the import and export facilities,
which is exactly what this tool produces.

Driving the import form with a session cookie is not an option either. The
[terms of use](https://letterboxd.com/terms-of-use/) (last updated December
2025) state:

> Except as explicitly authorized in these Terms, you must not employ any robot,
> spider, scraper, deep-link, or other automated data gathering or extraction
> tool, program, or algorithm to access, acquire, copy, or monitor any portion
> of the Service.

and:

> You agree to access the Service through the interface we provide.

So this tool stops at the file. Generating a CSV from your own data and
uploading it yourself through the official form is the supported path, and it is
the one Letterboxd recommends. There is also no undo after the import
confirmation step, which is one more reason to keep a human on that screen.

## Data sources

| Source | Provides | Identifiers |
|---|---|---|
| Simkl | Completed films, ratings, watchlist | TMDB, IMDb, Letterboxd slug |
| Plex | Watched films, ratings, view counts | TMDB, IMDb (from guids) |
| Tautulli | Watch history | Title and year only |

Simkl has no rewatch concept and no review text: both are edited in the
dashboard. Tautulli has no ratings and no ids, so it needs a TMDB key to be
useful.

## Output layout

| Path | Contents |
|---|---|
| `output/pending/` | CSV files waiting to be imported |
| `output/done/<timestamp>/` | CSV files already confirmed as imported |
| `data/movies.db` | Local database: films, watch data, export state |
| `data/simkl_token.json` | Simkl access token |
| `logs/` | Rotating logs, one file per command plus the weekly task log |

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `PRIMARY_SOURCE` | `simkl`, `plex` or `tautulli` | `simkl` |
| `SIMKL_CLIENT_ID` | Simkl app client id | - |
| `SIMKL_CLIENT_SECRET` | Simkl app client secret | - |
| `SIMKL_TOKEN_FILE` | Where the access token is stored | `data/simkl_token.json` |
| `SIMKL_CONVERT_TIMEZONE` | Convert Simkl timestamps to `LOCAL_TIMEZONE` before truncating | `false` |
| `PLEX_URL`, `PLEX_TOKEN` | Plex server and token | `http://localhost:32400` |
| `TAUTULLI_URL`, `TAUTULLI_API_KEY`, `TAUTULLI_USER_ID` | Tautulli instance | `http://localhost:8181`, -, `1` |
| `TMDB_API_KEY` | Optional enrichment; empty disables it | empty |
| `LOCAL_TIMEZONE` | Zone used to turn timestamps into calendar dates | `Europe/Paris` |
| `EXPORT_WATCHLIST` | Also write a watchlist file on export | `true` |
| `MAX_CSV_BYTES` | Split threshold, below the 1 MB hard limit | `950000` |
| `OUTPUT_DIR`, `DATA_DIR`, `LOG_DIR`, `DB_PATH` | Paths, relative to the project root | `output`, `data`, `logs`, `data/movies.db` |
| `LOG_LEVEL`, `CONSOLE_LOG_LEVEL` | Log verbosity for the file and the console | `INFO` |
| `WEB_PORT` | Dashboard port | `19876` |
| `OAUTH_PORT` | Simkl OAuth callback port, must match the redirect URI | `19877` |
| `SYNC_INTERVAL` | Dashboard background sync, in minutes; `0` disables it | `0` |

`.env` is git-ignored, and so is the token file. No credential is ever written
to a log.

## Docker

```bash
docker compose up -d                                   # dashboard
docker compose run --rm letterboxd-sync sync
docker compose run --rm letterboxd-sync export --incremental
```

Both ports are published: `19876` for the dashboard, `19877` for the Simkl OAuth
callback, which must match the redirect URI of your Simkl app.

## Tests

```powershell
$env:PYTHONIOENCODING = 'utf-8'
python -m pytest
```

The suite covers the CSV dialect (backslash escaping, commas, embedded
newlines, round-trips, 1 MB splitting), the Simkl mapping (dates, `Rating10`,
identifiers) and the incremental logic (new, changed, unchanged, confirmed).

## License

MIT
