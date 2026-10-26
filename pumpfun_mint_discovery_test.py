import os
import json
import urllib.request
import urllib.error

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


def get_account_keys(transaction):
    message = transaction.get("transaction", {}).get(
        "message", {}
    )

    keys = message.get("accountKeys", [])

    # Some RPC responses return account keys as objects.
    return [
        key.get("pubkey", "") if isinstance(key, dict) else key
        for key in keys
    ]


def get_all_instructions(transaction):
    message = transaction.get("transaction", {}).get(
        "message", {}
    )

    instructions = list(message.get("instructions", []))

    meta = transaction.get("meta") or {}

    for inner_group in meta.get("innerInstructions") or []:
        instructions.extend(inner_group.get("instructions", []))

    return instructions


def find_created_mints(transaction):
    keys = get_account_keys(transaction)
    instructions = get_all_instructions(transaction)
    mints = set()

    for instruction in instructions:
        program_id = instruction.get("programId")

        if not program_id:
            index = instruction.get("programIdIndex")

            if index is not None and index < len(keys):
                program_id = keys[index]

        if program_id != PUMP_FUN_PROGRAM:
            continue

        account_indexes = instruction.get("accounts", [])

        # Parsed instructions may provide account addresses directly.
        if account_indexes and isinstance(account_indexes[0], str):
            mint = account_indexes[0]

        # Raw JSON instructions provide account indexes.
        elif account_indexes and isinstance(account_indexes[0], int):
            mint_index = account_indexes[0]

            if mint_index >= len(keys):
                continue

            mint = keys[mint_index]

        else:
            continue

        instruction_data = instruction.get("data", "")

        # Report candidates for verification rather than assuming
        # every Pump.fun instruction creates a token.
        if mint:
            mints.add((mint, instruction_data))

    return mints


def main():
    signatures = rpc_call(
        "getSignaturesForAddress",
        [PUMP_FUN_PROGRAM, {"limit": 20}],
    ) or []

    print("Recent Pump.fun transactions:", len(signatures))

    discovered = set()
    checked = 0

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

        for mint, instruction_data in candidates:
            discovered.add(mint)

            print("Candidate mint:", mint)
            print("Transaction:", signature)
            print("Instruction data:", instruction_data)
            print("Verify this candidate before treating it as a new token.")

    print("Transactions checked:", checked)
    print("Unique candidate mints:", len(discovered))
    print("Discovery test completed.")


if __name__ == "__main__":
    main()
