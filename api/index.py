import os
import json
import tempfile
from functools import lru_cache
from fastapi import FastAPI, Query, Header, Response
from fastapi.responses import StreamingResponse
from ytmusicapi import YTMusic
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import requests

app = FastAPI()
yt = YTMusic(location="IN", language="en")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@lru_cache(maxsize=100) 
def get_stream_url_from_yt(video_id: str):
   ydl_opts = {
        'format': '251/140/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extractor_args': {

            'youtube': {'player_client': ['ios', 'android', 'web']}
        }
    }

    # 1. Check for cookies in the environment variables
    cookie_data = os.environ.get("YOUTUBE_COOKIES")
    temp_cookie_file = None

    if cookie_data:
        # 2. Create a secure temporary file
        temp_cookie_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt')
        
        # 3. Clean and write the cookie data
        clean_cookie_data = cookie_data.replace('\\n', '\n') 
        temp_cookie_file.write(clean_cookie_data)
        temp_cookie_file.flush() # Force write to disk immediately
        
        # 4. Point yt-dlp to this temporary file
        ydl_opts['cookiefile'] = temp_cookie_file.name

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            return info.get('url')
            
    finally:
        # 5. SECURITY: Always delete the temporary file immediately after extracting the URL
        if temp_cookie_file:
            temp_cookie_file.close()
            if os.path.exists(temp_cookie_file.name):
                os.remove(temp_cookie_file.name)

@app.get("/api/search")
def search_all(q: str = Query(...)):
    try:
        artists_results = yt.search(q, filter="artists", limit=1)[:1]
        songs_results = yt.search(q, filter="songs", limit=20)[:20]
        playlists_results = yt.search(q, filter="playlists", limit=10)[:10]

        mapped_results = []

        for item in artists_results:
            artist_id = item.get('browseId') 
            if not artist_id: continue
            
            thumbnails = item.get('thumbnails', [])
            image_url = thumbnails[-1]['url'] if thumbnails else ""
            if "=" in image_url: 
                image_url = image_url.split('=')[0] + "=w500-h500-l90-rj"

            mapped_results.append({
                "id": artist_id,
                "title": item.get('artist', item.get('title', 'Unknown Artist')),
                "subtitle": "Artist", 
                "type": "artist",
                "image": image_url
            })

        for item in songs_results:
            video_id = item.get('videoId')
            if not video_id: continue
            
            thumbnails = item.get('thumbnails', [])
            image_url = thumbnails[-1]['url'] if thumbnails else ""
            if "=" in image_url: 
                image_url = image_url.split('=')[0] + "=w500-h500-l90-rj"

            mapped_results.append({
                "id": video_id,
                "title": item.get('title', 'Unknown Title'),
                "subtitle": item.get('artists', [{}])[0].get('name', 'Unknown Artist'),
                "type": "song",
                "image": image_url,
                "duration": item.get('duration', '0:00')
            })


        for item in playlists_results:
            playlist_id = item.get('browseId') 
            if not playlist_id: continue
            
            thumbnails = item.get('thumbnails', [])
            image_url = thumbnails[-1]['url'] if thumbnails else ""
            if "=" in image_url: 
                image_url = image_url.split('=')[0] + "=w500-h500-l90-rj"

            mapped_results.append({
                "id": playlist_id,
                "title": item.get('title', 'Unknown Playlist'),
                "subtitle": f"Playlist • {item.get('author', 'YouTube Music')}", 
                "type": "playlist",
                "image": image_url,
                "trackCount": item.get('itemCount', '') 
            })

        return {
            "success": True,
            "data": mapped_results
        }

    except Exception as e:
        print(f"Search Error: {e}")
        return {
            "success": False,
            "error": str(e)
        }
        
@app.get("/api/search/songs")
def search_songs(q: str = Query(...)):
    results = yt.search(q, filter="songs")
    
    mapped_results = []
    
    for item in results:
        video_id = item.get('videoId')
        mapped_item = {
            "id": video_id,
            "name": item.get('title'),
            "type": "song",
            "year": item.get('year', "2024"),
            "duration": item.get('duration_seconds', 0),
            "album": {
                "name": item.get('album', {}).get('name', 'Single'),
                "id": item.get('album', {}).get('id', '')
            },
            "artists": {
                "primary": [
                    {
                        "name": a.get('name'),
                        "id": a.get('id'),
                        "role": "primary_artists"
                    } for a in item.get('artists', [])
                ]
            },
            "image": [
                {"quality": "50x50", "url": item['thumbnails'][0]['url']},
                {"quality": "150x150", "url": item['thumbnails'][-1]['url']},
                {"quality": "500x500", "url": item['thumbnails'][-1]['url'].replace('w120-h120', 'w500-h500')}
            ],
            "downloadUrl": [
                {"quality": "320kbps", "url": f"https://www.youtube.com/watch?v={video_id}"}
            ]
        }
        mapped_results.append(mapped_item)

    return {
        "success": True,
        "data": {
            "results": mapped_results
        }
    }

@app.get("/api/home")
def get_home_data():
    try:
        home_data = yt.get_home(limit=5)
        formatted_modules = []
        
        for shelf in home_data:
            title = shelf.get('title', 'Discover')
            contents = shelf.get('contents', [])
            
            mapped_contents = []
            for item in contents:
                item_id = item.get('videoId') or item.get('playlistId') or item.get('browseId')

                if not item_id:
                    continue

                if item.get('videoId'):
                    item_type = "song"
                elif item.get('playlistId'):
                    item_type = "playlist"
                else:
                    item_type = "album" 

                thumbnails = item.get('thumbnails', [])
                image_url = thumbnails[-1]['url'] if thumbnails else "https://via.placeholder.com/500"

                if "=" in image_url:
                    image_url = image_url.split('=')[0] + "=w500-h500-l90-rj"

                mapped_contents.append({
                    "id": item_id,
                    "title": item.get('title', 'Unknown Title'),
                    "subtitle": item.get('subtitle', ''), 
                    "type": item_type,
                    "image": image_url
                })
            
            if mapped_contents:
                formatted_modules.append({
                    "title": title,
                    "items": mapped_contents
                })
                
        return {
            "success": True,
            "data": formatted_modules
        }
        
    except Exception as e:
        return {
            "success": False, 
            "error": "Failed to fetch home data", 
            "details": str(e)
        }
        
@app.get("/api/playlist/{playlist_id}")
def get_playlist_details(playlist_id: str):
    try:
        if playlist_id.startswith("RD") or playlist_id.startswith("VL"):
            print(f"Fetching Watch Playlist: {playlist_id}")
            data = yt.get_watch_playlist(playlistId=playlist_id, limit=50)
            tracks = data.get('tracks', [])
            title = "Top Charts" # Watch playlists don't always return a title
        else:
            print(f"Fetching Standard Playlist: {playlist_id}")
            data = yt.get_playlist(playlist_id, limit=100)
            tracks = data.get('tracks', [])
            title = data.get('title', 'Playlist')

        mapped_tracks = []
        for item in tracks:
            video_id = item.get('videoId')
            if not video_id: continue
            thumbnails = item.get('thumbnails') or item.get('thumbnail') or []
            
            image_url = ""
            if thumbnails:
                image_url = thumbnails[-1].get('url', '')
                if "=" in image_url:
                    image_url = image_url.split('=')[0] + "=w500-h500-l90-rj"
                elif "googleusercontent" not in image_url:
                    image_url = image_url.replace("default.jpg", "hqdefault.jpg")
            duration = item.get('duration') or item.get('length') or item.get('duration_seconds') or "0:00"

            mapped_tracks.append({
                "id": video_id,
                "title": item.get('title', 'Unknown'),
                "subtitle": item.get('artists', [{}])[0].get('name', 'Unknown Artist'),
                "type": "song",
                "image": image_url,
                "duration": str(duration)
            })
            
        return {
            "success": True,
            "data": {
                "title": title,
                "tracks": mapped_tracks
            }
        }
        
    except Exception as e:
        print(f"Error: {e}")
        return {
            "success": False,
            "error": "This playlist type is currently restricted or the ID is invalid."
        }

@app.get("/api/artist/{artist_id}")
def get_artist_songs(artist_id: str):
    try:
        artist_data = yt.get_artist(artist_id)
        songs = artist_data.get("songs", {}).get("results", [])
        mapped_results = []

        for item in songs:
            video_id = item.get('videoId')
            if not video_id: continue
            
            thumbnails = item.get('thumbnails', [])
            image_url = thumbnails[-1]['url'] if thumbnails else ""
            if "=" in image_url: 
                image_url = image_url.split('=')[0] + "=w500-h500-l90-rj"
            artists_list = item.get('artists', [])
            if artists_list:
                all_singers = ", ".join([a.get('name') for a in artists_list if a.get('name')])
            else:
                all_singers = artist_data.get('name', 'Unknown Artist')

            plays_raw = item.get('views') or item.get('plays') or item.get('playCount') or ""
            plays_count = str(plays_raw)

            mapped_results.append({
                "id": video_id,
                "title": item.get('title', 'Unknown Title'),
                "subtitle": all_singers,
                "type": "song",
                "image": image_url,
                "duration": item.get('duration', '0:00'),
                "plays": plays_count 
            })

        return {
            "success": True,
            "artistName": artist_data.get('name', 'Unknown Artist'),
            "artistImage": artist_data.get('thumbnails', [{}])[-1].get('url', ''),
            "data": mapped_results
        }

    except Exception as e:
        print(f"Artist Fetch Error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/api/stream/{video_id}")
def get_audio_stream(video_id: str, range: str = Header(None)):
    try:
        direct_playback_url = get_stream_url_from_yt(video_id)
        print(f"Direct Playback URL for {video_id}: {direct_playback_url}")
            
        if not direct_playback_url:
            return {"success": False, "error": "Could not extract stream URL"}

        headers = {"Range": range} if range else {}
        response = requests.get(direct_playback_url, headers=headers, stream=True)
        
        def stream_chunks():
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if chunk:
                    yield chunk

        response_headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": response.headers.get("Content-Type", "audio/webm")
        }
        if "Content-Length" in response.headers: response_headers["Content-Length"] = response.headers["Content-Length"]
        if "Content-Range" in response.headers: response_headers["Content-Range"] = response.headers["Content-Range"]

        return StreamingResponse(
            stream_chunks(), 
            status_code=206 if range else 200,
            headers=response_headers
        )
        
    except Exception as e:
        get_stream_url_from_yt.cache_clear()
        print(f"Streaming Error: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/search/suggestions")
def get_suggestions(q: str = Query(...)):
    try:
        suggestions = yt.get_search_suggestions(q)
        return {"success": True, "data": suggestions}
    except Exception as e:
        return {"success": False, "error": str(e)}
        
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
