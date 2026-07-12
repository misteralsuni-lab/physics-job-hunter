# UAE market intel — placeholder

**Source:** https://www.youtube.com/watch?v=2HkM_VvBYzo
**Target use:** v2 rubric adjustments for the dual-pathway tutoring branch.

## Status

Pulled metadata on 21 June 2026 (`yt-dlp 2026.06.09`). Title returned as
**"Flora Residence by Bukhatir Group"** (1:15 duration, channel
"Markable International"). User flagged the URL as "UAE market" before
embedding — likely a tangential reference, not specifically tutoring
market intel. **No transcript available.** YouTube returned HTTP 429 on
the timedtext endpoint; the page has no native subtitles and ASR auto-
translated captions are not pulled.

## What we need to use this for the rubric

1. A real transcript or content summary of meaningful length.
2. Confirmation that this video contains tutoring-market commentary.

If either (1) or (2) is missing, do not feed this URL into the rubric or
proposal copy — there is nothing to refactor from.

## To retry

```bash
# Try again on a different network or after some hours
yt-dlp --write-auto-sub --sub-lang "en" --skip-download \
       --js-runtimes node \
       -o "/tmp/uae_video.%(ext)s" \
       "https://www.youtube.com/watch?v=2HkM_VvBYzo"
```

If 429 persists, install Chrome's native deps and use a real browser fetch:

```bash
sudo apt-get install -y libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 \
                         libcups2 libxkbcommon0 libxcomposite1 libxdamage1 \
                         libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
                         libcairo2 libasound2t64
```

Then `browser_navigate` will work and can render the YouTube page.
