# Installation

## Requirements

- Steam Deck or Steam Machine running SteamOS and Decky Loader.
- Internet access for initial setup and downloading artwork.
- A personal SteamGridDB API key for artwork search.
- Space for video tools, downloaded sources and prepared media.

GabeCubeAura and a Faceplate are optional. They are not needed for the main display.

## Install DAS

Download the versioned plugin ZIP from the [latest release](https://github.com/Alyenax/Decky-Animated-Screensaver/releases/latest).
In Decky Loader, open its developer settings and select **Install plugin from ZIP**,
then choose the downloaded archive. Enable Developer mode in Decky's General
settings first if needed. Install the ZIP directly; do not unpack it first.
The plugin appears as **Animated Screensaver** in Decky.

After installation, open **Animated Screensaver** in Decky and complete [Setup](Setup.md). Build your first collection using [Preparation](Preparation.md).

## Select the installed collection in Steam

After DAS reports that the collection is installed, open:

**Steam → Settings → Customization → Screensaver → decky-animated-screensaver**

Set the inactivity delay in **Steam → Settings → Power**. DAS can open the Power settings from its Playback page. Selecting a screensaver and choosing its inactivity delay are separate Steam settings.

A DAS preview does not select or activate Steam’s screensaver. Check playback by leaving Steam idle after choosing the installed collection.

## Update the plugin

The public build checks for releases every 24 hours by default. The first scheduled check is also 24 hours after startup. You can disable automatic checking or check manually without waiting for that interval, when no update operation is in progress. Downloading an update and confirming its installation are separate actions. Close running games and finish or stop preparation before installing.

Stable is the default public channel. Beta also includes public beta releases;
private alpha releases are excluded. Public checks need no GitHub sign-in.

Use the [release page](https://github.com/Alyenax/Decky-Animated-Screensaver/releases) for downloads and checksums.
