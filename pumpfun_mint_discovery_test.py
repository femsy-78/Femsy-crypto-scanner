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

        print("Transaction account count:", len(keys))
        print("Transaction instruction count:", len(instructions))
        for instruction in instructions:
        program_index = instruction.get("programIdIndex")
        program_id = (keys[program_index]
        if program_index is not None and program_index < len(keys)
        else "UNKNOWN"
                     )
        print("Program ID:", program_id)
        print("Instruction data:", instruction.get("data", ""))
        print("Account indexes:", instruction.get("accounts", []))
        for instruction in instructions:
            program_index = instruction.get("programIdIndex")
            if program_index is None or program_index >= len(keys):
                continue

            program_id = keys[program_index]
            if isinstance(program_id, dict):
                program_id = program_id.get("pubkey")

            if program_id == PUMP_FUN_PROGRAM:
                print(
                    "Pump.fun instruction data:",
                    str(instruction.get("data", ""))[:40],
                )

    print("Candidate token mints:", len(discovered_mints))
    print("Diagnostic test completed.")


if __name__ == "__main__":
    main()
