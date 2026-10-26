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

    for entry in signatures:
        signature = entry.get("signature")

        if not signature:
            continue

        transaction = rpc_call(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 1,
                },
            ],
        )

        if not transaction:
            continue

        message = transaction.get("transaction", {}).get("message", {})
        account_keys = message.get("accountKeys", [])

        print("Transaction:", signature)
        print("Accounts examined:", len(account_keys))

    print("Discovery test completed.")
    print(
        "Note: This test retrieves recent transactions; "
        "it does not yet verify newly created token mints."
    )


if __name__ == "__main__":
    main()
