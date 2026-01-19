import os, base64, tempfile
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException
from ytmusicapi import YTMusic

app = FastAPI()

def get_ytmusic() -> YTMusic:
    b64 = os.getenv("YTMUSIC_OAUTH_B64")
    if not b64:
        raise RuntimeError("Missing YTMUSIC_OAUTH_B64")
    data = base64.b64decode(b64).decode("utf-8")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tmp.write(data.encode("utf-8"))
    tmp.close()

    return YTMusic(tmp.name)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/csv-to-playlist")
async def csv_to_playlist(
    file: UploadFile = File(...),
    playlist_name: str = "Imported from CSV",
    privacy: str = "PRIVATE"   # PRIVATE, UNLISTED, PUBLIC
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
