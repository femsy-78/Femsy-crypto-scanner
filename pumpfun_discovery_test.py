import os
import json
import urllib.request
import urllib.error

API_KEY = os.environ.get("HELIUS_API_KEY")

if not API_KEY:
    raise RuntimeError("HELIUS_API_KEY is missing")

RPC_URL = (
    "https://mainnet.helius-rpc.com/"
    f"?api-key={API_KEY}"
)

PUMP_FUN_PROGRAM = (
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
)

payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "getSignaturesForAddress",
    "params": [
        PUMP_FUN_PROGRAM,
        {"limit": 10}
    ]
}

request = urllib.request.Request(
    RPC_URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    if "error" in data:
        raise RuntimeError(data["error"])

    signatures = data.get("result", [])

    print("Helius connection: SUCCESS")
    print("Recent program transactions:", len(signatures))

    for item in signatures:
        print(
            item.get("signature"),
            "slot:",
            item.get("slot")
        )

except Exception as error:
    print("Pump.fun discovery test failed:", error)
    raise
