import os
import io
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import HTMLResponse
from ytmusicapi import YTMusic

app = FastAPI()

def get_ytmusic() -> YTMusic:
    # Render secret files are typically mounted at /etc/secrets/<filename>
    for p in ("oauth.json", "/etc/secrets/oauth.json"):
        if os.path.exists(p):
            return YTMusic(p)
    raise RuntimeError("Missing oauth.json (checked ./oauth.json and /etc/secrets/oauth.json)")

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>CSV → YouTube Music Playlist</title>
        <style>
          body { font-family: -apple-system, system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 40px; }
          .box { max-width: 720px; }
          input, select, button { font-size: 16px; padding: 10px; margin: 6px 0; width: 100%; }
          button { cursor: pointer; }
          .small { color: #666; font-size: 14px; }
          code { background:#f4f4f4; padding:2px 6px; border-radius:4px; }
        </style>
      </head>
      <body>
        <div class="box">
          <h2>CSV → YouTube Music Playlist</h2>
          <p class="small">CSV must include a <code>title</code> column. Optional: <code>artist</code>.</p>

          <form action="/csv-to-playlist" method="post" enctype="multipart/form-data">
            <label>Playlist name</label>
            <input name="playlist_name" value="Imported from CSV" />

            <label>Privacy</label>
            <select name="privacy">
              <option value="PRIVATE" selected>PRIVATE</option>
              <option value="UNLISTED">UNLISTED</option>
              <option value="PUBLIC">PUBLIC</option>
            </select>

            <label>CSV file</label>
            <input type="file" name="file" accept=".csv" required />

            <button type="submit">Create Playlist</button>
          </form>

          <p class="small">API docs: <a href="/docs">/docs</a></p>
        </div>
      </body>
    </html>
    """

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/csv-to-playlist")
async def csv_to_playlist(
    file: UploadFile = File(...),
    playlist_name: str = Form("Imported from CSV"),
    privacy: str = Form("PRIVATE")  # PRIVATE, UNLISTED, PUBLIC
):
    # Basic extension check
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a .csv file")

    # Read upload bytes
    content = await file.read()

    # Prevent pandas EmptyDataError (empty upload)
    if not content or len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file was empty. Re-select the CSV file and try again."
        )

    # Parse CSV safely
    try:
        df = pd.read_csv(io.BytesIO(content))
    except pd.errors.EmptyDataError:
        raise HTTPException(
            status_code=400,
            detail="CSV appears empty or unreadable. Make sure it has a header row like: title,artist"
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse CSV: {type(e).__name__}: {e}"
        )

    # Normalize column names (strip spaces + lowercase)
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Accept common title column names
    title_candidates = ["title", "track", "track_name", "song", "name"]
    title_col = next((c for c in title_candidates if c in df.columns), None)

    if not title_col:
        raise HTTPException(
            400,
            f"CSV must include a title column. Found columns: {list(df.columns)}"
        )

    # Create playlist + add items
    try:
        ytmusic = get_ytmusic()

        playlist_id = ytmusic.create_playlist(
            playlist_name,
            description="Created by CSV importer",
            privacy_status=privacy
        )

        video_ids = []
        for _, row in df.iterrows():
            title = str(row.get(title_col, "")).strip()

            # Optional artist column support (also normalized)
            artist = ""
            if "artist" in df.columns:
                artist = str(row.get("artist", "")).strip()

            if not title:
                continue

            q = f"{title} {artist}".strip()
            results = ytmusic.search(q, filter="songs")
            if results:
                video_ids.append(results[0]["videoId"])

        if video_ids:
            ytmusic.add_playlist_items(playlist_id, video_ids)

        return {
            "playlistId": playlist_id,
            "playlistUrl": f"https://music.youtube.com/playlist?list={playlist_id}",
            "addedCount": len(video_ids)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Playlist creation failed: {type(e).__name__}: {e}")
