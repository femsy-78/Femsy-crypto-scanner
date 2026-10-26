import os
import json
import urllib.request

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

discovered = set()

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
                "maxSupportedTransactionVersion": 0,
            },
        ],
    )

    if not transaction:
        continue

    message = (
        transaction.get("transaction", {})
        .get("message", {})
    )

    account_keys = message.get("accountKeys", [])

    for account in account_keys:
        if isinstance(account, dict):
            address = account.get("pubkey")
        else:
            address = account

        if address:
            discovered.add(address)

    for instruction in message.get("instructions", []):
        program_id = instruction.get("programId")

        if program_id != PUMP_FUN_PROGRAM:
            continue

        parsed = instruction.get("parsed")

        if isinstance(parsed, dict):
            info = parsed.get("info", {})

            mint = info.get("mint")
            if mint:
                discovered.add(mint)

print("Unique addresses examined:", len(discovered))
print("Candidate addresses:")

for address in sorted(discovered):
    print(address)

print(
    "NOTE: These are candidate addresses, "
    "not verified newly created token mints."
)

if name == "main":
main()
