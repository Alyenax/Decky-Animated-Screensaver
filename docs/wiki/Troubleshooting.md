# Troubleshooting

| Symptom | Check or action |
| --- | --- |
| Artwork search fails | Test the saved SteamGridDB key in Setup and check the connection. |
| Video tools are missing | Download or verify them in Setup. Wait for Ready. |
| No animation for a game | Choose another animation or allow still images. Without fallback, the game can be skipped. |
| Saved changes do not appear | Prepare and install the collection again. Saving choices alone does not update Steam. |
| Preparation asks you to close a game | Exit the running game, then retry the operation. |
| Preparation was interrupted | Read the progress state; resume when available or retry missing / changed media. |
| Steam does not start the screensaver | Check its selected screensaver and Power inactivity delay. A preview does not change them. |
| Faceplate is unavailable | Check the connection in GCA and DAS’s optional output setting. TV playback can continue. |
| TV and Faceplate differ in timing | Check playback mode and visual alignment. Synchronisation is experimental. |
| Update check finds no public release | Check connectivity and the selected Stable/Beta channel, then try Check for updates now. If needed, inspect the release page. |

## Check the relevant result

A working source preview confirms that the source can be displayed. A completed preparation confirms that files were generated. Installation makes a collection available to Steam. None of these alone confirms visible Faceplate playback.

If a replacement fails, check the previous installed collection before deleting anything. Change or retry the affected artwork rather than clearing the whole collection first.

## Save a local report

Open **Settings → Storage and assistance → Save local diagnostic**. DAS shows the saved `diagnostic.json` file’s exact path and lets you view the
report. It stays on this device with owner-only permissions; nothing is uploaded.
Keys and media bytes are excluded.

The local report retains the complete evidence formerly collected for online
reports: JSAUX state and delivery, player/relay and Steam browser traces,
local delivery checks, preparation errors, artwork metadata and discovery.
It also includes workspace, tools, installation, events and update status.
Full Faceplate details are preserved under `jsaux_delivery`. Saving the report
does not reconnect the device, cancel a task or start preparation.

When reporting a problem, include the DAS version, the action you took, the full error message and whether TV, preview or Faceplate playback was affected. Review any file before sharing it.
