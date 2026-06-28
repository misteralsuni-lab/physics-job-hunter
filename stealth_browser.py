"""
Stealth browser for bot.sannysoft.com / Intoli bot detection tests.

Uses Camoufox (custom Firefox build) with route interception to inject
fingerprint patches before any page scripts execute.

Usage:
    python3 stealth_browser.py
"""

import asyncio
import io
import zstandard as zstd
from camoufox import AsyncCamoufox

# ── Injected script: runs before any page script ──────────────────────

INJECT_SCRIPT_STR = """<script>
window.chrome = {
  runtime: {},
  loadTimes: function() {},
  csi: function() {},
  app: {isInstalled: false}
};
var _origQuery = navigator.permissions.query.bind(navigator.permissions);
navigator.permissions.query = function(p) {
  return p.name === 'notifications'
    ? Promise.resolve({state: Notification.permission})
    : _origQuery(p);
};
</script>"""

INJECT_SCRIPT = INJECT_SCRIPT_STR.encode("ascii")

# ── Route handler: decompress zstd HTML and inject our script ─────────

def _decompress_zstd(body: bytes) -> bytes:
    """Decompress zstd-encoded content (streaming, no content-size header)."""
    dctx = zstd.ZstdDecompressor()
    reader = dctx.stream_reader(io.BytesIO(body))
    return reader.read()


async def inject_into_html(route):
    """Intercept the main HTML page, decompress zstd, inject script, fulfill."""
    resp = await route.fetch()
    headers = dict(resp.headers)
    body = await resp.body()

    ce = headers.get("content-encoding", "")
    if "zstd" in ce:
        body = _decompress_zstd(body)
        del headers["content-encoding"]
        headers.pop("transfer-encoding", None)
        headers["content-length"] = str(len(body))

    body = body.replace(b"<script", INJECT_SCRIPT + b"<script", 1)
    await route.fulfill(body=body, headers=headers)


# ── Main ──────────────────────────────────────────────────────────────

async def launch_browser():
    """Create a Camoufox browser instance with stealth route interception."""
    browser = AsyncCamoufox(
        headless=False,
        humanize=True,
        os="windows",
        locale="en-US",
    )
    return await browser.__aenter__()


async def main():
    try:
        async with AsyncCamoufox(
            headless=False,
            humanize=True,
            os="windows",
            locale="en-US",
        ) as browser:

            ctx = await browser.new_context()
            page = await ctx.new_page()
            page.on("pageerror", lambda _: None)

            # Only intercept the main page (not sub-resources like JS/CSS/images)
            await page.route("https://bot.sannysoft.com/", inject_into_html)
            await page.goto("https://bot.sannysoft.com", wait_until="domcontentloaded")
            await asyncio.sleep(3)

            rows = await page.evaluate("""() => {
                const trs = document.querySelector('table')?.querySelectorAll('tr');
                if (!trs) return [];
                return Array.from(trs).map(tr => {
                    const tds = tr.querySelectorAll('td');
                    if (tds.length < 2) return null;
                    const name = tds[0].textContent.trim();
                    const result = tds[1].textContent.trim();
                    const passed = tds[1].classList.contains('passed');
                    return { name, result, passed };
                }).filter(r => r !== null);
            }""")

            print("Intoli / Sannysoft Bot Detection Results:")
            print("─" * 65)
            for r in rows:
                icon = "✅" if r["passed"] else "❌"
                print(f"  {icon}  {r['name']:35s} {r['result']}")
            print("─" * 65)

            print("\n[*] Browser will close automatically in 60 seconds (or press Ctrl+C)...")
            await asyncio.sleep(60)

    except KeyboardInterrupt:
        print("\n[*] Closing browser...")
    except Exception as e:
        print(f"[*] Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
