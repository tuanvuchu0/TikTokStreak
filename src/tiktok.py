from urllib.parse import parse_qs, quote, urlparse
from playwright.async_api import Page, async_playwright

from storage import SESSION_FILE, TIKTOK_HOME_URL


def get_message_url(user_id: str) -> str:
    return f"https://www.tiktok.com/messages?lang=en-GB&u={quote(user_id, safe='')}"


async def get_user_id(page: Page, username: str) -> str:
    username = username.strip().lstrip("@")

    if not username:
        raise ValueError("Username cannot be empty")

    profile_url = f"https://www.tiktok.com/@{quote(username, safe='')}"

    await page.goto(
        profile_url,
        wait_until="domcontentloaded",
    )

    profile = page.locator("#ProfilePage")

    try:
        await profile.wait_for(state="attached", timeout=20_000)

        data = await profile.evaluate(
            "(element) => JSON.parse(element.textContent)"
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not read profile data for @{username}."
        ) from exc

    image_url = (
        data.get("mainEntity", {}).get("image")
        if isinstance(data, dict)
        else None
    )

    if not image_url:
        raise RuntimeError(
            f"Could not find mainEntity.image for @{username}"
        )

    user_id = parse_qs(urlparse(image_url).query).get("userId", [None])[0]

    if not user_id:
        raise RuntimeError(
            f"Could not find TikTok userId for @{username}"
        )

    return user_id


async def login() -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(
                TIKTOK_HOME_URL,
                wait_until="domcontentloaded",
            )

            print("\nPlease log in to TikTok in the Chromium window.")
            print("After logging in successfully, return to terminal.")
            input("Press Enter to save session... ")

            await context.storage_state(path=str(SESSION_FILE))
            print(f"Session saved at: {SESSION_FILE}")

        finally:
            await context.close()
            await browser.close()


async def open_authenticated_page(headless: bool = True):
    if not SESSION_FILE.exists():
        raise FileNotFoundError(
            "No TikTok session found. Please run: streak-saver login"
        )

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=headless)

    context = await browser.new_context(
        storage_state=str(SESSION_FILE),
    )

    page = await context.new_page()
    return playwright, browser, context, page


async def send_direct_message(page: Page, user_id: str, message: str) -> None:
    url = get_message_url(user_id)
    await page.goto(url, wait_until="domcontentloaded")

    input_selectors = [
        'div[data-e2e="message-input-area"] div[contenteditable="true"]',
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"]',
        'textarea',
    ]

    chat_input = None
    for selector in input_selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=8000)
            chat_input = locator
            break
        except Exception:
            continue

    if chat_input is None:
        raise RuntimeError(
            f"Could not find chat input for user_id={user_id}. "
            "The recipient may have disabled direct messages or the session has expired."
        )

    await chat_input.click()
    await page.wait_for_timeout(300)

    await chat_input.press_sequentially(message, delay=50)
    await page.wait_for_timeout(400)

    await chat_input.press("Enter")

    try:
        send_btn = page.locator(
            'button[data-e2e="message-send-btn"], button[aria-label="Send"], svg[data-e2e="message-send-btn"]'
        ).first
        if await send_btn.is_visible(timeout=1000):
            await send_btn.click()
    except Exception:
        pass

    await page.wait_for_timeout(2000)

