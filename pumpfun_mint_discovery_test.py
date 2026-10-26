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
        result = json.loads(response.read().decode("utf-8"))

    if "error" in result:
        raise RuntimeError(result["error"])

    return result.get("result")


def main():
    signatures = rpc_call(
        "getSignaturesForAddress",
        [PUMP_FUN_PROGRAM, {"limit": 10}],
    ) or []

    print("Recent Pump.fun transactions:", len(signatures))

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

        message = transaction.get("transaction", {}).get(
            "message", {}
        )
        keys = message.get("accountKeys", [])
        instructions = message.get("instructions", [])

        print("Transaction account count:", len(keys))
        print("Transaction instruction count:", len(instructions))

        for instruction in instructions:
            index = instruction.get("programIdIndex")

            if index is None or index >= len(keys):
                continue

            program_id = keys[index]

            print("Program ID:", program_id)
            print("Instruction data:", instruction.get("data", ""))
            print("Account indexes:", instruction.get("accounts", []))

    print("Diagnostic test completed.")


if __name__ == "__main__":
    main()
