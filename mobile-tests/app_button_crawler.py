"""
Button crawler for the Boost app (Android, LambdaTest real devices).

Logs in once via boost_actions.action_login, then from the post-login home
screen it SCROLLS through the full length of every screen (not just what's
visible without scrolling -- Android lazy-renders list content, so a single
snapshot misses anything below the fold) and clicks every clickable element
it finds, recording what happened. Whenever a click opens a NEW screen, that
screen is queued and crawled the same way (breadth-first), so it discovers
screens you don't already know about, not just ones you point it at.

How it gets back to a screen: it restarts the app and replays the taps that
led there (the "path"), re-logging in first if the restart actually landed
back on the login screen (see ensure_logged_in). Slower than pressing Back,
but much more reliable. Combined with the full-screen scroll before every
click, a real run is noticeably slow -- that's the trade for thoroughness.

What "all" does NOT cover, on purpose or by real limitation -- read this
before trusting a clean report as exhaustive:
  - MAX_DEPTH (default 6): screens more than 6 taps from Home aren't
    reached at all.
  - MAX_ACTIONS (default 400): hard stop on total clicks for the whole run;
    a large app can exceed this before finishing.
  - SKIP_WORDS: anything labelled delete/logout/pay/purchase/checkout/
    withdraw/redeem/convert/cash out/etc. is deliberately NOT clicked (see
    below) -- so whatever screen sits behind one of those stays
    undiscovered. That's intentional, not a bug.
  - Only elements Android's accessibility tree marks clickable=true are
    found. Custom gesture-only UI (swipe carousels, long-press, drag-to-
    reorder, raw Canvas/WebView content) won't be seen or triggered.
  - Only the login form gets real typed input (via action_login). Any other
    screen gated behind filling in a field before something becomes usable
    won't be explored past that point.
  - Screens whose content changes between visits (e.g. a feed with new
    items) can get mistaken for a "new" screen each time, since the
    fingerprint is a hash of what's currently on screen.
Tune MAX_DEPTH/MAX_ACTIONS/SKIP_WORDS at the top of this file if these
defaults don't fit a given run.

IMPORTANT -- OTP rate limit: the real API allows 3 OTP requests per phone
number per hour (confirmed in the JMeter performance work, see
performance/README.md). If the app does NOT keep you logged in across a
plain terminate+relaunch, every restart would need a fresh OTP and the
crawl would start failing with rate-limit errors after 3 restarts, for the
rest of that hour. ensure_logged_in() only calls action_login when the
login screen is actually detected (so a normal session-persisting restart
costs nothing), and MAX_LOGIN_ATTEMPTS hard-stops the whole crawl well
before that happens, rather than silently burning the hourly quota.

Output:
  crawl_report.csv -> one row per element: screen, element, status, detail, leads_to
  screens/S*.png   -> a screenshot of every screen discovered
  LambdaTest dashboard -> video + device logs of the whole run

Setup:
  pip install -r requirements.txt
  export LT_USERNAME=... LT_ACCESS_KEY=...
  export TEST_ID_NUMBER=... TEST_PHONE_LOCAL=...   (same test identity conventions as boost_actions.py)
  python app_button_crawler.py
"""
import csv
import hashlib
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import deque

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy

from boost_actions import APP_ID, HUB_URL, action_login, tap_by_text

# ---------------- CONFIG ----------------
MAX_DEPTH = 12             # how many taps deep to go from the home screen
MAX_ACTIONS = 1500         # hard stop so a run can't go forever
MAX_LOGIN_ATTEMPTS = 2     # hard stop on real (OTP-consuming) re-logins -- see module docstring
WAIT_AFTER_CLICK = 1.5     # seconds to let the screen settle after a tap
WAIT_AFTER_LAUNCH = 3.0

# Buttons whose label contains any of these are NOT clicked (logged as SKIP).
# Boost-specific additions beyond the obvious ones: withdraw/redeem/convert,
# since those move real points/vouchers on a real account.
SKIP_WORDS = ["delete", "remove", "logout", "log out", "sign out",
              "pay", "purchase", "buy", "checkout", "deactivate", "reset",
              "withdraw", "redeem", "convert", "cash out"]

REPORT = "crawl_report.csv"
SCREEN_DIR = "screens"
APP_FOREGROUND = 4  # value returned by query_app_state when app is in front


# ---------------- DRIVER ----------------
def make_driver():
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.app = APP_ID
    options.set_capability("lt:options", {
        "username": os.environ["LT_USERNAME"],
        "accessKey": os.environ["LT_ACCESS_KEY"],
        "deviceName": os.environ.get("LT_DEVICE", "Galaxy S23"),
        "platformVersion": os.environ.get("LT_PLATFORM_VERSION", "13"),
        "isRealMobile": True,
        "build": "button-crawler",
        "name": "app_button_crawler",
        "video": True,
        "devicelog": True,
    })
    return webdriver.Remote(HUB_URL, options=options)


def make_state():
    return {
        "id_number": os.environ["TEST_ID_NUMBER"],
        "phone": os.environ["TEST_PHONE_LOCAL"],
        "otp": os.environ.get("TEST_OTP") or "123456",
        "screens": [],
        "login_count": 0,
    }


def restart_app(driver, app_id):
    try:
        driver.terminate_app(app_id)
    except Exception:
        pass
    driver.activate_app(app_id)
    time.sleep(WAIT_AFTER_LAUNCH)


def ensure_logged_in(driver, state):
    """Only runs the real (OTP-consuming) login flow if the login screen is
    actually on screen right now -- a session-persisting restart should see
    the home screen directly and this is then a no-op (just the field check
    below, no network calls)."""
    on_login_screen = (
        driver.find_elements(AppiumBy.XPATH, "//android.widget.TextView[@text='ID number']")
        or driver.find_elements(AppiumBy.XPATH, "//*[contains(@text,'Get Started')]")
    )
    if not on_login_screen:
        return
    state["login_count"] += 1
    if state["login_count"] > MAX_LOGIN_ATTEMPTS:
        raise RuntimeError(
            f"ensure_logged_in: hit MAX_LOGIN_ATTEMPTS ({MAX_LOGIN_ATTEMPTS}) -- "
            "the app isn't keeping the session across restarts, so continuing "
            "would burn through the 3-OTP-per-phone-per-hour limit. Stopping "
            "the crawl here; see the module docstring.")
    action_login(driver, state)


# ---------------- READING THE SCREEN ----------------
def xlit(s):
    """Safe XPath string literal (handles quotes in labels)."""
    if "'" not in s:
        return f"'{s}'"
    if '"' not in s:
        return f'"{s}"'
    return "concat('" + s.replace("'", "',\"'\",'") + "')"


def snapshot(driver, app_id):
    """Return (list of clickable elements, fingerprint of the screen)."""
    root = ET.fromstring(driver.page_source.encode("utf-8"))
    elements, counts = [], {}

    for node in root.iter():
        a = node.attrib
        if a.get("clickable") != "true" or a.get("enabled") != "true":
            continue
        if a.get("package") and a.get("package") != app_id:
            continue  # ignore system UI / other apps
        cls, rid = a.get("class", ""), a.get("resource-id", "")
        desc, text = a.get("content-desc", ""), a.get("text", "")
        # use text in the identity only if nothing more stable exists
        sig = (cls, rid, desc, "" if (rid or desc) else text)
        label = text or desc or rid.split("/")[-1] or cls.split(".")[-1]
        nums = list(map(int, re.findall(r"-?\d+", a.get("bounds", "[0,0][0,0]"))))
        center = ((nums[0] + nums[2]) // 2, (nums[1] + nums[3]) // 2)

        occ = counts.get(sig, 0)  # nth element with the same identity
        counts[sig] = occ + 1
        elements.append({"sig": sig, "occ": occ, "label": label.strip()[:80],
                          "center": center})

    raw = driver.current_activity + "|" + "|".join(sorted(str(e["sig"]) for e in elements))
    fp = hashlib.md5(raw.encode()).hexdigest()
    return elements, fp


def xpath_for(sig):
    cls, rid, desc, text = sig
    xp = f"//{cls}[@clickable='true']"
    if rid: xp += f"[@resource-id={xlit(rid)}]"
    if desc: xp += f"[@content-desc={xlit(desc)}]"
    if text: xp += f"[@text={xlit(text)}]"
    return xp


# ---------------- SCROLLING ----------------
# Android lazy-renders list/scroll content: anything below the fold simply
# isn't in page_source yet, so a single snapshot() only ever sees what's
# currently on screen. Everything below scrolls the full length of the
# screen to find every clickable element, not just the ones visible without
# scrolling -- this is the actual "scrolls the app" half of the crawler.

def _swipe(driver, direction):
    size = driver.get_window_size()
    w, h = size["width"], size["height"]
    before = driver.page_source
    driver.execute_script("mobile: swipeGesture", {
        "left": int(w * 0.1), "top": int(h * 0.2),
        "width": int(w * 0.8), "height": int(h * 0.6),
        "direction": direction, "percent": 0.9,
    })
    time.sleep(0.8)
    return driver.page_source != before


def scroll_down(driver):
    """Reveals lower content. Returns True if anything actually moved."""
    return _swipe(driver, "up")


def scroll_to_top(driver, max_swipes=15):
    for _ in range(max_swipes):
        if not _swipe(driver, "down"):
            break


def collect_all_elements(driver, app_id, max_scrolls=15):
    """Scroll from the top of the current screen all the way down,
    accumulating every distinct clickable element seen at any scroll
    position. Returns (elements, fingerprint) -- the fingerprint covers the
    whole scrollable screen, not just one viewport, so it stays comparable
    between an initial visit and a post-click re-check (both scroll the
    full length the same way)."""
    scroll_to_top(driver)
    seen, all_elements, sig_parts = set(), [], []
    for _ in range(max_scrolls):
        elements, _ = snapshot(driver, app_id)
        for el in elements:
            has_id = any(el["sig"][1:])
            dedupe_key = el["sig"] if has_id else (el["sig"], el["occ"])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            all_elements.append(el)
            sig_parts.append(str(el["sig"]))
        if not scroll_down(driver):
            break
    raw = driver.current_activity + "|" + "|".join(sorted(sig_parts))
    fp = hashlib.md5(raw.encode()).hexdigest()
    return all_elements, fp


def scroll_into_view_and_find(driver, sig, occ, max_scrolls=15):
    """The element may be below the fold after returning to a screen
    (restart + path replay always lands back at the top) -- scroll down
    step by step, re-checking after each one, until it's actually
    rendered."""
    scroll_to_top(driver)
    for _ in range(max_scrolls):
        els = driver.find_elements(AppiumBy.XPATH, xpath_for(sig))
        if len(els) > occ:
            return els[occ]
        if not scroll_down(driver):
            break
    return None


# ---------------- ACTIONS ----------------
def click_step(driver, step):
    """Scroll the element described by step into view and click it."""
    el = scroll_into_view_and_find(driver, step["sig"], step["occ"])
    if el is None:
        raise RuntimeError(f"could not scroll {step['label']!r} into view")
    el.click()  # real click: fails if not actually clickable
    time.sleep(WAIT_AFTER_CLICK)
    return "clicked"


def go_to(driver, app_id, state, path):
    """Restart the app, make sure we're logged in, then replay the taps that
    lead to a screen."""
    restart_app(driver, app_id)
    ensure_logged_in(driver, state)
    for step in path:
        try:
            click_step(driver, step)
        except Exception:
            return False
    return True


def in_app(driver, app_id):
    try:
        return driver.query_app_state(app_id) == APP_FOREGROUND
    except Exception:
        return False


# ---------------- CRAWL ----------------
def crawl():
    os.makedirs(SCREEN_DIR, exist_ok=True)
    driver = make_driver()
    state = make_state()
    results, failed = [], 0

    try:
        app_id = driver.current_package
        print("App:", app_id)

        ensure_logged_in(driver, state)
        _, fp0 = collect_all_elements(driver, app_id)
        screens = {fp0: "S0"}
        driver.get_screenshot_as_file(f"{SCREEN_DIR}/S0.png")
        queue = deque([([], "S0")])
        tested = set()  # avoid re-testing shared buttons (nav bars, tabs) on every screen
        actions = 0

        while queue and actions < MAX_ACTIONS:
            path, screen = queue.popleft()
            print(f"\n=== Screen {screen} (depth {len(path)}) ===")
            if not go_to(driver, app_id, state, path):
                results.append([screen, "-", "UNREACHABLE", "could not replay path", ""])
                continue
            elements, here_fp = collect_all_elements(driver, app_id)
            on_screen = True

            for el in elements:
                if actions >= MAX_ACTIONS:
                    break
                has_id = any(el["sig"][1:])
                key = (el["sig"], el["occ"]) if has_id else (here_fp, el["sig"], el["occ"])
                if key in tested:
                    continue
                tested.add(key)

                if any(w in el["label"].lower() for w in SKIP_WORDS):
                    results.append([screen, el["label"], "SKIP", "risky word in label", ""])
                    print("SKIP ", el["label"])
                    continue

                if not on_screen and not go_to(driver, app_id, state, path):
                    results.append([screen, el["label"], "UNREACHABLE", "", ""])
                    continue

                actions += 1
                leads_to = ""
                try:
                    note = click_step(driver, el)
                    on_screen = False
                    if not in_app(driver, app_id):
                        status, detail = "LEFT_APP", "app closed/crashed or opened another app"
                        failed += 1
                    else:
                        _, new_fp = collect_all_elements(driver, app_id)
                        if new_fp == here_fp:
                            status, detail = "OK", f"{note}, screen unchanged"
                            on_screen = True
                        else:
                            status, detail = "OK", note
                            if new_fp not in screens:
                                screens[new_fp] = f"S{len(screens)}"
                                driver.get_screenshot_as_file(
                                    f"{SCREEN_DIR}/{screens[new_fp]}.png")
                            if len(path) + 1 < MAX_DEPTH:
                                queue.append((path + [el], screens[new_fp]))
                            leads_to = screens[new_fp]
                except Exception as e:
                    status, detail = "FAIL", type(e).__name__
                    failed += 1
                    on_screen = False

                results.append([screen, el["label"], status, detail, leads_to])
                print(f"{status:5} {el['label']}" + (f" -> {leads_to}" if leads_to else ""))

        print(f"\nDone: {len(screens)} screens, {actions} clicks, {failed} problems, "
              f"{state['login_count']} real logins")
        driver.execute_script(f"lambda-status={'failed' if failed else 'passed'}")
    except RuntimeError as e:
        print(f"\nSTOPPED EARLY: {e}")
    finally:
        with open(REPORT, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["screen", "element", "status", "detail", "leads_to"])
            w.writerows(results)
        print("Report written to", REPORT)
        driver.quit()


if __name__ == "__main__":
    crawl()
