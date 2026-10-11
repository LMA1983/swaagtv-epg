# SWAAGTV EPG

Builds `swaagtv.xml` (XMLTV) daily from TV Passport's Swaag TV (WPVN-DT3) listings.

## Setup
1. Create a new GitHub repo and upload everything in this folder (keep `.github/workflows/update-epg.yml` in place).
2. Repo > Settings > Actions > General > Workflow permissions: **Read and write**.
3. Actions tab > "Update EPG" > **Run workflow** once to test. It then runs daily.
4. In your player, add this as the XMLTV/EPG URL (replace USER and REPO):
   `https://raw.githubusercontent.com/USER/REPO/main/swaagtv.xml`
5. In your playlist, set the SWAAGTV channel's `tvg-id="swaagtv"`.

## Check these on first run
- Time zone: the script assumes TV Passport shows Eastern. If shows land an hour off, set `SOURCE_TZ` (for example `America/Chicago`) in the workflow's `env:`.
- If the log says "no programs parsed", the site's layout changed and `parse_day()` needs adjusting.
- Listings are fetched politely (2 s between pages). Check TV Passport's terms before relying on this.
