import os
import json
import hashlib
import urllib.request

API_KEY = os.environ.get("HELIUS_API_KEY")

if not API_KEY:
    raise RuntimeError("HELIUS_API_KEY is missing")

RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"

PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


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

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))

    if "error" in result:
        raise RuntimeError(f"Helius RPC error: {result['error']}")

    return result.get("result")


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
    instruction_discriminator("create"): "create",
    bytes([86, 47, 157, 73, 202, 202, 173, 107]): "create_v2",
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
        print("Pump.fun instruction data:", data)
        print("Decoded discriminator:", decoded_data[:8].hex())
        print(
            "Known discriminators:",
            {
                name: value.hex()
                for value, name in CREATE_DISCRIMINATORS.items()
            },
        )

        if len(decoded_data) < 8:
            continue

        instruction_name = CREATE_DISCRIMINATORS.get(
            decoded_data[:8]
        )

        # Ignore buys, sells, and all other Pump.fun instructions.
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

         if mint: found.append({
        "mint": mint,
        "instruction": instruction_name,
    })


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

            unique_mints[mint] = signature

            print("Pump.fun creation candidate:", mint)
            print("Instruction:", candidate["instruction"])
            print("Transaction:", signature)
            print(
                "Explorer:",
                f"https://solscan.io/token/{mint}",
            )
    print("Creation instructions matched:", sum(
    1 for mint in unique_mints))
    print("Transactions checked:", checked)
    print("Unique creation candidates:", len(unique_mints))
    print("Discovery test completed.")


if __name__ == "__main__":
    main()
