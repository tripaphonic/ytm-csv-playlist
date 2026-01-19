import os
import io
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import HTMLResponse
from ytmusicapi import YTMusic


app = FastAPI()

def get_ytmusic() -> YTMusic:
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
    playlist_name: str = "Imported from CSV",
    privacy: str = "PRIVATE"  # PRIVATE, UNLISTED, PUBLIC
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a .csv file")

    content = await file.read()
    df = pd.read_csv(pd.io.common.BytesIO(content))

    if "title" not in df.columns:
        raise HTTPException(400, "CSV must include a 'title' column")

    ytmusic = get_ytmusic()

    playlist_id = ytmusic.create_playlist(
        playlist_name,
        description="Created by CSV importer",
        privacy_status=privacy
    )

    video_ids = []
    for _, row in df.iterrows():
        title = str(row.get("title", "")).strip()
        artist = str(row.get("artist", "")).strip() if "artist" in df.columns else ""

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
