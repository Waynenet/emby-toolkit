# ETK MediaInfo Bridge

Minimal Emby plugin used to import ETK-formatted media information without
running Emby's remote probe. It targets Emby 4.9.x.

The authenticated endpoint accepts the first object stored in
`p115_mediainfo_cache.mediainfo_json`:

```http
POST /Items/{Id}/ETKMediaInfo
Content-Type: application/json
X-Emby-Token: <admin-api-key>

{
  "MediaSourceInfo": { "MediaStreams": [] },
  "Chapters": []
}
```

Each request replaces the embedded streams for that exact Emby Item ID while
preserving external streams already detected by Emby. Repeating the same
request is idempotent.

The plugin also listens for Emby item refreshes. For ETK STRM paths it waits
for the refresh to settle, fetches the formatted cache from ETK by pick code or
SHA1, and restores the media streams automatically.

Build with the .NET 8 SDK:

```bash
dotnet build -c Release
```

Install `bin/Release/netstandard2.0/ETKMediaInfoBridge.dll` in Emby's plugin
directory and restart Emby. ETK treats a non-success response from this
endpoint as an injection failure and does not fall back to remote probing or
sidecar files. Emby must be able to reach the ETK URL stored in the STRM file.
