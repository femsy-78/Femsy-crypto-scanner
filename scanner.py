import os
import time
import json
import urllib.request
import urllib.parse
import urllib.error

from safety_scanner import check_token_safety

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

BASE_URL = "https://api.dexscreener.com"

# Initial research filters — we'll tune these after testing.
MIN_LIQUIDITY_USD = 8000
MIN_VOLUME_5M_USD = 1000
MIN_TXNS_5M = 10
MAX_PAIR_AGE_HOURS = 3
MAX_PRICE_CHANGE_5M = 80

SEEN_FILE = "seen_tokens.json"


def api_get(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "FemsyCryptoScanner/1.0"}
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }).encode()

    request = urllib.request.Request(url, data=payload)

    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode())

    if not result.get("ok"):
        raise RuntimeError("Telegram rejected the message")


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        # Keep the stored history manageable.
        return set(data[-3000:])

    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as file:
        json.dump(list(seen)[-3000:], file)


def get_solana_profiles():
    url = f"{BASE_URL}/token-profiles/latest/v1"
    data = api_get(url)

    return [
        item for item in data
        if item.get("chainId") == "solana"
        and item.get("tokenAddress")
    ]


def get_token_pairs(token_address):
    url = (
        f"{BASE_URL}/token-pairs/v1/solana/"
        f"{urllib.parse.quote(token_address, safe='')}"
    )

    try:
        data = api_get(url)

        if isinstance(data, list):
            return data

    except Exception as error:
        print(f"Pair lookup failed: {error}")

    return []


def analyse_pair(pair):
    liquidity = (pair.get("liquidity") or {}).get("usd") or 0
    volume = pair.get("volume") or {}
    txns = pair.get("txns") or {}
    m5 = txns.get("m5") or {}
    price_change = pair.get("priceChange") or {}

    buys = m5.get("buys") or 0
    sells = m5.get("sells") or 0
    total_txns = buys + sells

    volume_5m = volume.get("m5") or 0
    change_5m = price_change.get("m5") or 0

    created_at = pair.get("pairCreatedAt")

    if not created_at:
        return None

    age_hours = max(
        0,
        (time.time() * 1000 - created_at) / 3_600_000
    )

    if liquidity < MIN_LIQUIDITY_USD:
        return None

    if volume_5m < MIN_VOLUME_5M_USD:
        return None

    if total_txns < MIN_TXNS_5M:
        return None

    # Avoid alerting on pairs already showing extreme
    # five-minute price expansion.
    if change_5m > MAX_PRICE_CHANGE_5M:
        return None

    if age_hours > MAX_PAIR_AGE_HOURS:
        return None

    # Buy transaction counts are not unique-wallet counts.
    buy_ratio = buys / total_txns if total_txns else 0

    if age_hours <= 0.5:
        category = "🆕 EARLY WATCH"
    else:
        category = "🎯 QUALITY SETUP"

    if buy_ratio >= 0.60:
        flow = "Buying activity is elevated"
    elif buy_ratio <= 0.40:
        flow = "Selling activity is elevated"
    else:
        flow = "Buy/sell activity is mixed"

    base = pair.get("baseToken") or {}
    name = base.get("name") or "Unknown"
    symbol = base.get("symbol") or "UNKNOWN"
    address = base.get("address") or ""

    return {
        "category": category,
        "name": name,
        "symbol": symbol,
        "address": address,
        "url": pair.get("url") or "",
        "liquidity": liquidity,
        "volume_5m": volume_5m,
        "buys": buys,
        "sells": sells,
        "buy_ratio": buy_ratio,
        "age_hours": age_hours,
        "change_5m": change_5m,
        "flow": flow,
        "pair_address": pair.get("pairAddress", "")
    }


def format_alert(item):
    safety = item.get("safety", {})
    checks = safety.get("checks", {})
    warnings = safety.get("warnings", [])

    if not safety.get("data_complete", False):
        safety_status = "⚠️ INCOMPLETE — DO NOT ASSUME SAFE"
    else:
        mint = checks.get("mint_authority", {}).get("status", "UNKNOWN")
        freeze = checks.get("freeze_authority", {}).get("status", "UNKNOWN")

        concentration = checks.get(
            "top_10_account_concentration", {}
        )

        concentration_status = concentration.get(
            "status", "UNKNOWN"
        )
        concentration_percent = concentration.get(
            "estimated_percent"
        )

        safety_status = (
            f"Mint authority: {mint}\n"
            f"Freeze authority: {freeze}\n"
            f"Top-10 account concentration: {concentration_status}"
        )

        if concentration_percent is not None:
            safety_status += f" ({concentration_percent:.2f}%)"

    warning_text = (
        "\n".join(f"⚠️ {warning}" for warning in warnings)
        if warnings
        else "No warnings reported by these checks."
    )

    return (
        f"{item['category']}\n\n"
        f"Token: {item['name']} ({item['symbol']})\n"
        f"Age: {item['age_hours']:.2f} hours\n"
        f"Liquidity: ${item['liquidity']:,.0f}\n"
        f"5m volume: ${item['volume_5m']:,.0f}\n"
        f"5m buys: {item['buys']}\n"
        f"5m sells: {item['sells']}\n"
        f"5m price change: {item['change_5m']:.1f}%\n"
        f"Flow: {item['flow']}\n\n"
        f"🛡️ TOKEN SAFETY\n"
        f"{safety_status}\n\n"
        f"Warnings:\n{warning_text}\n\n"
        f"Token address:\n{item['address']}\n\n"
        f"Chart: {item['url']}\n\n"
        "⚠️ Research alert, not a buy signal.\n"
        "These checks do not guarantee token safety or profit.\n"
        "Verify holder ownership, liquidity quality, "
        "token extensions and wallet activity manually."
    )


def main():
    seen = load_seen()
    found = 0

    print("Femsy Crypto Scanner starting...")

    profiles = get_solana_profiles()

    # Limit API requests during the first version.
    addresses = list(dict.fromkeys(
        item["tokenAddress"] for item in profiles
    ))[:30]

    for address in addresses:
        pairs = get_token_pairs(address)

        for pair in pairs:
            if pair.get("chainId") != "solana":
                continue

            item = analyse_pair(pair)

            if not item:
                continue

            pair_id = item["pair_address"] or item["address"]

            if not pair_id or pair_id in seen:
                continue

            send_telegram(format_alert(item))
            seen.add(pair_id)
            found += 1

            # Avoid sending too many messages at once.
            time.sleep(1)

        # Keep API requests spaced out.
        time.sleep(0.25)

    save_seen(seen)

    print(f"Scan complete. New alerts sent: {found}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Scanner error: {error}")
        raise
