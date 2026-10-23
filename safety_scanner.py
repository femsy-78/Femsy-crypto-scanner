import os
import json
import urllib.request
import urllib.error

HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY")

if HELIUS_API_KEY:
    SOLANA_RPC = (
        "https://mainnet.helius-rpc.com/"
        f"?api-key={HELIUS_API_KEY}"
    )
else:
    SOLANA_RPC = "https://api.mainnet-beta.solana.com"


def rpc_call(method, params):
    """Call the Solana RPC endpoint."""

    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }).encode("utf-8")

    request = urllib.request.Request(
        SOLANA_RPC,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))

    if "error" in result:
        raise RuntimeError(
            result["error"].get("message", "RPC error")
        )

    return result.get("result", {}).get("value")
    
def check_token_safety(mint_address):
    """Inspect basic Solana token risks."""

    report = {
        "mint_address": mint_address,
        "checks": {},
        "warnings": [],
        "data_complete": False,
        "ownership_data_complete": False
    }

    try:
        # Read the token mint account.
        account = rpc_call(
            "getAccountInfo",
            [
                mint_address,
                {"encoding": "jsonParsed", "commitment": "confirmed"}
            ]
        )

        if not account:
            report["warnings"].append(
                "Mint account not found. Verify the token address."
            )
            return report

        parsed = account.get("data", {}).get("parsed", {})
        info = parsed.get("info", {})
        token_type = parsed.get("type")

        if token_type != "mint":
            report["warnings"].append(
                "Account could not be verified as a token mint."
            )
            return report

        # Check mint and freeze authorities.
        mint_authority = info.get("mintAuthority")
        freeze_authority = info.get("freezeAuthority")

        report["checks"]["mint_authority"] = {
            "status": "RISK" if mint_authority else "REVOKED",
            "authority": mint_authority
        }

        report["checks"]["freeze_authority"] = {
            "status": "RISK" if freeze_authority else "REVOKED",
            "authority": freeze_authority
        }

        if mint_authority:
            report["warnings"].append(
                "Mint authority exists; additional tokens may be created."
            )

        if freeze_authority:
            report["warnings"].append(
                "Freeze authority exists; token accounts may be frozen."
            )

        # Read total token supply.
        supply = rpc_call("getTokenSupply", [mint_address])

        if not supply:
            raise RuntimeError("Token supply data unavailable")

        total_raw = int(supply.get("amount", "0"))

        if total_raw <= 0:
            raise RuntimeError("Token supply is zero or unavailable")

        # Read the ten largest token accounts.
        largest = rpc_call(
            "getTokenLargestAccounts",
            [mint_address]
        )

        if not isinstance(largest, dict):
            raise RuntimeError("Largest-account data unavailable")

        accounts = largest.get("value")

        if not isinstance(accounts, list):
            raise RuntimeError("Largest-account list unavailable")

        top_raw = sum(
            int(item.get("amount", "0"))
            for item in accounts
        )

        concentration = (top_raw / total_raw) * 100

        report["checks"]["top_10_account_concentration"] = {
            "status": (
                "HIGH" if concentration >= 50
                else "MODERATE" if concentration >= 20
                else "LOW"
            ),
            "estimated_percent": round(concentration, 2),
            "note": (
                "This estimates concentration in token accounts, not "
                "verified individual holders. Liquidity pools and special "
                "accounts may affect the estimate."
            )
        }

        report["ownership_data_complete"] = False
        report["data_complete"] = True

    except Exception as error:
        report["warnings"].append(
            "Safety checks incomplete: " + str(error)
        )

    return report

if __name__ == "__main__":
    address = input("Enter a Solana token mint address: ").strip()

    if not address:
        print("No token address supplied.")
    else:
        result = check_token_safety(address)
        print(json.dumps(result, indent=2))
