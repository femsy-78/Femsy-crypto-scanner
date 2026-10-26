import os
import json
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
        data = json.loads(response.read().decode("utf-8"))

    if "error" in data:
        raise RuntimeError(data["error"])

    return data.get("result")


def main():
    signatures = rpc_call(
        "getSignaturesForAddress",
        [PUMP_FUN_PROGRAM, {"limit": 10}],
    ) or []

    print("Recent Pump.fun transactions:", len(signatures))

    discovered_mints = set()

    for entry in signatures:
        signature = entry.get("signature")

        if not signature:
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
            continue

        meta = transaction.get("meta") or {}

        if meta.get("err") is not None:
            continue

        message = transaction.get("transaction", {}).get(
            "message", {}
        )

        keys = message.get("accountKeys", [])
        instructions = message.get("instructions", [])

        for instruction in instructions:
            program_id_index = instruction.get("programIdIndex")

            if program_id_index is None:
                continue

            if program_id_index >= len(keys):
                continue

            program_id = keys[program_id_index]

            if isinstance(program_id, dict):
                program_id = program_id.get("pubkey")

            if program_id != PUMP_FUN_PROGRAM:
                continue

            account_indexes = instruction.get("accounts", [])

            # Pump.fun create instructions commonly include the
            # mint as the second account. Verify the instruction
            # discriminator before accepting that account.
            raw_data = instruction.get("data", "")

            if not isinstance(raw_data, str):
                continue

            try:
                import base64

                decoded = base64.b64decode(
                    raw_data + "=" * (-len(raw_data) % 4)
                )
            except Exception:
                continue

            # Anchor instruction discriminator for "create":
            # first 8 bytes of SHA256("global:create").
            import hashlib

            create_discriminator = hashlib.sha256(
                b"global:create"
            ).digest()[:8]

            if decoded[:8] != create_discriminator:
                continue

            if len(account_indexes) < 2:
                continue

            mint_index = account_indexes[0]

            if isinstance(mint_index, dict):
                mint_address = mint_index.get("pubkey")
            elif isinstance(mint_index, int) and mint_index < len(keys):
                mint_address = keys[mint_index]
                if isinstance(mint_address, dict):
                    mint_address = mint_address.get("pubkey")
            else:
                mint_address = None

            if mint_address:
                discovered_mints.add(mint_address)

    print("Candidate token mints:", len(discovered_mints))

    for mint in sorted(discovered_mints):
        print("Mint:", mint)

    print(
        "Note: Validate each candidate against transaction "
        "account ordering before using it for trading alerts."
    )


if __name__ == "__main__":
    main()
