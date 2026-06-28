from camoufox import Camoufox

# Initialize the browser
with Camoufox() as browser:
    # Create a new page (tab)
    page = browser.new_page()
    # Go to the website
    page.goto('https://bot.sannysoft.com')
    # Keep it open so you can see the result
    input("Check the browser, then press Enter here to close...")
    # Clean exit
    browser.close()
