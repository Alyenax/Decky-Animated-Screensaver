# Settings and backups

## Advanced settings

Open **Settings → Advanced**. **All TV settings** exposes the detailed playback and preparation controls. **View all saved settings** shows TV, Faceplate and interface settings; update preferences and device calibration are included for reference. Credentials are omitted.

Change one setting at a time when comparing results. Update the collection afterwards when the change affects prepared or installed playback.

## Export settings JSON

Select **Export settings JSON**. A message displays **JSON saved:** followed by the file’s location. Keep a copy if you want to restore those settings later.

The export contains TV settings, Faceplate settings and the saved interface
mode/layout. The file is saved under `Documents/AnimatedScreensaver` in your
home folder, with owner-only permissions. The result message gives its exact path.

It does not contain API keys, games, artwork files, update preferences or device
calibration. Interface language is saved separately in the local interface and
is not included. This is a settings backup, not a complete collection backup.

## Import settings JSON

1. Select **Choose JSON to import** and choose an exported settings file.
2. Check the selected path and confirm the replacement.
3. Read the result message. DAS saves the previous settings before importing and shows their location.
4. Update the collection to apply relevant changes to Steam.

Import is unavailable during conflicting operations such as preparation or update installation.

## Storage and assistance

Review local storage and the available cleanup actions before removing files. Cached source images and prepared media serve different purposes: clearing reusable files can make a later preparation download or convert them again.

For a playback problem, use the local support tools described in [Troubleshooting](Troubleshooting.md). Saving a local report does not upload it.
