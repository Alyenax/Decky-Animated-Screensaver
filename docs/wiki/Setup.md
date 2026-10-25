# Setup

Open **Settings → Setup**. The three sections appear in this order.

## 1 · SteamGridDB

1. Select **Log in with Steam** to open SteamGridDB.
2. Use **Get my API key** to open its API keys page.
3. Paste your key into DAS and select **Verify** to save and check it.
4. Use **Test saved key** when you need to check an existing key.

A successful saved-key test shows a green **✓ Saved key verified** message. If verification fails, retry or save another key. The key is stored on this device and is used for requests to SteamGridDB.

## 2 · Video tools

Select **Download** if the tools are missing. This downloads **FFmpeg 9.0.2,
ffprobe and their shared Linux x86_64 libraries**, about **64 MB**, from
**BtbN/FFmpeg-Builds on GitHub**. They analyse and prepare images and animations.

Before downloading, the interface shows the **exact installation folder**
reported by Decky: `cinema-tools-v1` inside Animated Screensaver’s Decky settings
directory. The path depends on your Decky installation. The downloaded archive
is extracted there and checked before use; the temporary archive is then removed.
This installs tools for DAS, rather than replacing the system’s FFmpeg.

Wait for **Ready**. If these downloaded tools are already installed, **Verify**
checks them. If compatible system tools are already available, DAS can report
Ready without downloading this optional distribution.

**Allow still images** lets preparation use a still image when no animation is available. You can also choose a still image for a particular game. See [Artwork](Artwork.md).

## 3 · Steam library import - optional

**Skip this if you only use installed games or search for games.**

Import adds games you own, including titles not installed on this device. Enter your Steam profile and a Steam Web API key, then select **Import**. Steam’s Game details must be public for the import.

The fields stay on the device until you request the import. The request then goes directly to Steam over HTTPS. The Steam Web API key is not saved or exported; it is cleared after the attempt. Imported game records are saved locally. This key is separate from your SteamGridDB key.

Next: [add games to your collection](Games-and-Collection.md).
