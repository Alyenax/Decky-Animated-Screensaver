# Public updates

Animated Screensaver 1.0.0, published by Alyenax.

- Anonymous GET requests only, pinned to the Animated Screensaver repository's
  release metadata and release assets. No OAuth, credentials, content writes or
  private alpha channel. Existing private token files are ignored and preserved.
- Stable by default; Beta includes stable and public beta releases. Drafts and
  alpha prereleases never qualify.
- Automatic metadata check every 1440 minutes, including the first startup wait.
  Disabling checks is supported. Manual checks remain immediate. Legacy 5/15/60/
  720-minute preferences are ignored; automatic-install preferences are ignored
  and rejected by the public configuration RPC.
- Checking or displaying a notification never downloads or installs anything.
  Native Decky update buttons remain visible in the quick and full views.
- Download is explicit, cancelable, bounded and verified against SHA256SUMS and
  the GitHub digest when supplied. The exact tree manifest, plugin identity,
  archive envelope and filesystem boundaries remain validated.
- Installation needs a second explicit confirmation and a verified download.
  The updater checks the game/preparation state under the work-start lock before launching its helper, uses
  the system Python/systemd path, and retains the backend-health rollback.
- A failed anonymous check reports unavailable public releases. There is no
  private authentication fallback. Release metadata and files are served by the public repository.
- All diagnostics stay local. Full JSAUX evidence is retained in
  `diagnostic.json`, alongside plugin/workspace/update context. The local report
  is readable in the interface and its saved path is displayed.

Automated checks establish software/package behaviour. Real SteamOS installation,
Decky restart, controller focus and physical playback require separate acceptance.
