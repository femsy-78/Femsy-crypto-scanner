import os
import json
import base64
import hashlib
import urllib.request
import urllib.error
import time

from solders.pubkey import Pubkey

API_KEY = os.environ.get("HELIUS_API_KEY")

if not API_KEY:
    raise RuntimeError("HELIUS_API_KEY is missing")

RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"

PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

def get_bonding_curve_address(mint):
    """Derive the Pump.fun bonding-curve account address."""
    try:
        mint_pubkey = Pubkey.from_string(mint)
        program_pubkey = Pubkey.from_string(PUMP_FUN_PROGRAM)

        bonding_curve, bump = Pubkey.find_program_address(
            [b"bonding-curve", bytes(mint_pubkey)],
            program_pubkey,
        )

        return str(bonding_curve)

    except ValueError as error:
        print(f"Invalid mint address {mint}: {error}")
        return None

def get_bonding_curve_account(mint):
    """Fetch the derived bonding-curve account from Helius."""
    address = get_bonding_curve_address(mint)

    if not address:
        return None

    account = rpc_call(
        "getAccountInfo",
        [
            address,
            {
                "encoding": "base64",
                "commitment": "confirmed",
            },
        ],
    )

    if not account or not account.get("value"):
        print("Bonding-curve account unavailable:", mint)
        return None

    value = account["value"]

    print("Bonding-curve address:", address)
    print("Bonding-curve owner:", value.get("owner"))
    data = value.get("data") or ["", "base64"]
    encoded_data = data[0] if data else ""
    decoded_data = base64.b64decode(encoded_data) if encoded_data else b""

    print("Bonding-curve data length (bytes):", len(decoded_data))

    return value

def rpc_call(method, params):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }

    request = urllib.request.Request(
        RPC_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    for attempt in range(5):
        try:
            with urllib.request.urlopen(
                request, timeout=30
            ) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )

            if "error" in result:
                raise RuntimeError(
                    f"Helius RPC error: {result['error']}"
                )

            return result.get("result")

        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == 4:
                raise

            retry_after = error.headers.get("Retry-After")
            try:
                wait_seconds = float(retry_after) if retry_after else 5 * (attempt + 1)
            except ValueError:
                wait_seconds = 5 * (attempt + 1)

            print(
                f"Helius rate limit (429). "
                f"Retrying in {wait_seconds:g} seconds..."
            )
            time.sleep(wait_seconds)


def base58_decode(value):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0

    for char in value:
        if char not in alphabet:
            return b""
        number = number * 58 + alphabet.index(char)

    raw = (
        number.to_bytes((number.bit_length() + 7) // 8, "big")
        if number
        else b""
    )

    leading_zeros = len(value) - len(value.lstrip("1"))
    return b"\x00" * leading_zeros + raw

def instruction_discriminator(name):
    return hashlib.sha256(
        f"global:{name}".encode("utf-8")
    ).digest()[:8]


CREATE_DISCRIMINATORS = {
    bytes.fromhex("181ec828051c0777"): "create",
    bytes.fromhex("33e685a4017f83ad"): "create_v2",
    bytes.fromhex("d6904cec5f8b31b4"): "create_v2",
}


def get_account_keys(transaction):
    message = transaction.get("transaction", {}).get(
        "message", {}
    )

    keys = message.get("accountKeys", [])

    # Support account keys represented as strings or objects.
    keys = [
        key.get("pubkey", "") if isinstance(key, dict) else key
        for key in keys
    ]

    # Include addresses loaded through address lookup tables.
    meta = transaction.get("meta") or {}
    loaded = meta.get("loadedAddresses") or {}

    keys.extend(loaded.get("writable", []))
    keys.extend(loaded.get("readonly", []))

    return keys

def get_dexscreener_data(mint):
    """Retrieve market data for a token from DexScreener."""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "FemsySolanaScanner/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        print(f"Market data unavailable for {mint}: {error}")
        return None

    pairs = data.get("pairs") or []

    # Only consider Solana pairs for this token.
    pairs = [
        pair for pair in pairs
        if pair.get("chainId") == "solana"
    ]

    if not pairs:
        print(f"UNVERIFIED — no DexScreener pair found: {mint}")
        return None

    # Use the pair with the greatest reported USD liquidity.
    pair = max(
        pairs,
        key=lambda item: (
            (item.get("liquidity") or {}).get("usd") or 0
        ),
    )

    liquidity = (pair.get("liquidity") or {}).get("usd")

    print("DEBUG — pair address:", pair.get("pairAddress"))
    print("DEBUG — DEX ID:", pair.get("dexId"))
    print("DEBUG — liquidity object:", pair.get("liquidity"))
    print("DEBUG — pair type:", pair.get("labels"))
    print("DEBUG — market cap:", pair.get("marketCap"))
    print("DEBUG — FDV:", pair.get("fdv"))
    print("DEBUG — volume:", pair.get("volume"))

    market_cap = pair.get("marketCap")
    if market_cap is None:
        market_cap = pair.get("fdv")

    volume_5m = (pair.get("volume") or {}).get("m5")
    created_at = pair.get("pairCreatedAt")

    age_minutes = None
    if created_at:
        age_minutes = (time.time() * 1000 - created_at) / 60000

    return {
        "mint": mint,
        "age_minutes": age_minutes,
        "market_cap": market_cap,
        "liquidity": liquidity,
        "volume_5m": volume_5m,
        "pair_url": pair.get("url"),
    }


def qualifies_for_market_filter(item):
    """Return True only when all four market filters pass."""
    if not item:
        return False

    age = item.get("age_minutes")
    market_cap = item.get("market_cap")
    liquidity = item.get("liquidity")
    volume = item.get("volume_5m")

    if any(value is None for value in (
        age, market_cap, liquidity, volume
    )):
        return False

    return (
        5 <= age <= 15
        and 20_000 <= market_cap <= 30_000
        and 25_000 <= liquidity <= 80_000
        and 80_000 <= volume <= 200_000
    )


def get_all_instructions(transaction):
    message = transaction.get("transaction", {}).get(
        "message", {}
    )

    instructions = list(message.get("instructions", []))

    meta = transaction.get("meta") or {}

    for group in meta.get("innerInstructions") or []:
        instructions.extend(group.get("instructions", []))

    return instructions


def find_created_mints(transaction):
    meta = transaction.get("meta") or {}

    # Never report token candidates from failed transactions.
    if meta.get("err") is not None:
        return []

    keys = get_account_keys(transaction)
    instructions = get_all_instructions(transaction)
    found = []

    for instruction in instructions:
        program_id = instruction.get("programId")

        if not program_id:
            program_index = instruction.get("programIdIndex")

            if (
                program_index is None
                or program_index < 0
                or program_index >= len(keys)
            ):
                continue

            program_id = keys[program_index]

        if program_id != PUMP_FUN_PROGRAM:
            continue

        data = instruction.get("data", "")
        decoded_data = base58_decode(data)

        if len(decoded_data) < 8:
            continue

        instruction_name = CREATE_DISCRIMINATORS.get(
            decoded_data[:8]
        )
        print("Decoded discriminator:", decoded_data[:8].hex())
        print(
        "Known discriminators:",
        [key.hex() for key in CREATE_DISCRIMINATORS],
        )

        # Ignore buys, sells, and other Pump.fun instructions.
        if instruction_name is None:
            continue

        accounts = instruction.get("accounts", [])

        if instruction_name == "create":
            mint_index = 0
        elif instruction_name == "create_v2":
            mint_index = 2
        else:
            continue

        if len(accounts) <= mint_index:
            continue

        mint_account = accounts[mint_index]

        if isinstance(mint_account, int):
            if mint_account < 0 or mint_account >= len(keys):
                continue
            mint = keys[mint_account]
        elif isinstance(mint_account, str):
            mint = mint_account
        else:
            continue

        if mint:
            found.append({
                "mint": mint,
                "instruction": instruction_name,
            })

    return found

def main():
    signatures = rpc_call(
        "getSignaturesForAddress",
        [PUMP_FUN_PROGRAM, {"limit": 100}],
    ) or []

    print("Recent Pump.fun transactions:", len(signatures))

    checked = 0
    unique_mints = {}

    for entry in signatures:
        signature = entry.get("signature")

        if not signature or entry.get("err"):
            continue

        transaction = rpc_call(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "json",
                    "maxSupportedTransactionVersion": 1,
                },
            ],
        )

        if not transaction:
            print("Transaction data unavailable:", signature)
            continue

        checked += 1
        candidates = find_created_mints(transaction)

                for candidate in candidates:
            mint = candidate["mint"]

            if mint in unique_mints:
                continue

            print("Checking bonding curve for:", mint)
            curve_account = get_bonding_curve_account(mint)

            if curve_account:
                print("Bonding-curve account fetched successfully:", mint)
            else:
                print("Bonding-curve account not verified:", mint)

            market_data = get_dexscreener_data(mint)

            if not market_data:
                print("UNVERIFIED — skipping token:", mint)
                continue

            if not qualifies_for_market_filter(market_data):
                print("REJECTED — market filters:", mint)
                print("Market data:", market_data)
                continue

            unique_mints[mint] = signature

            print("QUALIFIED — market filters passed:", mint)
            print("Market data:", market_data)
            print("Instruction:", candidate["instruction"])
            print("Transaction:", signature)
            print("Explorer:", f"https://solscan.io/token/{mint}")
            print("DexScreener:", market_data["pair_url"])

    print("Transactions checked:", checked)
    print("Unique qualifying candidates:", len(unique_mints))
    print("Discovery test completed.")


if __name__ == "__main__":
    main()
