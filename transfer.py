#!/usr/bin/env python3
"""Fund wallet by transfering token"""

import os
import sys
import yaml
import time
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

# Enable HD wallet features (for deriving addresses from mnemonic)
Account.enable_unaudited_hdwallet_features()

# --- CONFIGURATION ---

# Load environment variables from .env
load_dotenv()

# Destination wallet is derived from the mnemonic
MNEMONIC = os.getenv("MNEMONIC", "").strip()
if not MNEMONIC:
    raise Exception("Please ensure MNEMONIC is set in the .env file.")
dest_account = Account.from_mnemonic(MNEMONIC)
DEST_WALLET = dest_account.address

RPC_URL = os.getenv("RPC_URL")
if not RPC_URL:
    raise Exception("Please ensure RPC_URL is set in the .env file.")

# The sender's private key
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
if not PRIVATE_KEY:
    raise Exception("Please ensure PRIVATE_KEY is set in the .env file.")

# Load tokens from token.yml
with open("token.yml", "r") as token_file:
    tokens_data = yaml.safe_load(token_file)

tokens = tokens_data.get("tokens", [])
if not tokens:
    raise Exception("No tokens found in token.yml under the 'tokens' key.")

# Minimal ERC20 ABI for balanceOf and transfer
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
]

# --- SETUP WEB3 & ACCOUNTS ---

w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    raise Exception("Failed to connect to the RPC endpoint.")

chain_id = w3.eth.chain_id

# Derive the sender account from PRIVATE_KEY
sender_account = Account.from_key(PRIVATE_KEY)
sender_address = sender_account.address
print(f"Sender Address: {sender_address}")
print(f"Destination Address (from mnemonic): {DEST_WALLET}")

# --- UTILITY FUNCTIONS ---


def find_token_by_symbol(symbol: str):
    """Return the token dict from tokens list matching the symbol (case-insensitive)"""
    for token in tokens:
        if token.get("symbol", "").lower() == symbol.lower():
            return token
    return None


def transfer_token(token, token_quantity):
    token_name = token.get("name", "Unknown Token")
    token_symbol = token.get("symbol", "")
    token_address = token.get("address")
    decimals = token.get("decimals", 18)

    if not token_address:
        print(f"Token {token_name} has no address defined. Exiting.")
        return

    print(
        f"\nProcessing transfer for {token_name} ({token_symbol}) at address {token_address}"
    )

    # Instantiate token contract
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
    )

    # Check the sender's token balance
    try:
        balance = contract.functions.balanceOf(sender_address).call()
    except Exception as e:
        print(f"Error fetching balance for {token_symbol}: {e}")
        return

    human_balance = balance / (10**decimals)
    print(f"Sender token balance: {human_balance} {token_symbol}")
    
    transfer_quantity = Web3.to_wei(token_quantity, "ether")

    if balance < transfer_quantity:
        print(f"Insufficient balance of {token_symbol} to transfer. Exiting.")
        return

    # Build the transaction to transfer the full token balance to DEST_WALLET
    try:
        nonce = w3.eth.get_transaction_count(sender_address)
        gas_price = w3.eth.gas_price

        tx = contract.functions.transfer(
            Web3.to_checksum_address(DEST_WALLET), transfer_quantity
        ).build_transaction(
            {
                "from": sender_address,
                "nonce": nonce,
                "gasPrice": gas_price,
                "chainId": chain_id,
            }
        )

        # Estimate gas and update transaction
        estimated_gas = w3.eth.estimate_gas(tx)
        tx["gas"] = estimated_gas

        print(
            f"Transaction details: nonce={nonce}, gas={estimated_gas}, gasPrice={gas_price}"
        )
    except Exception as e:
        print(f"Error building transaction for {token_symbol}: {e}")
        return

    # Sign the transaction with the sender's private key
    try:
        signed_tx = sender_account.sign_transaction(tx)
    except Exception as e:
        print(f"Error signing transaction for {token_symbol}: {e}")
        return

    # Send the transaction
    try:
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"Transaction sent! TX hash: {tx_hash.hex()}")
    except Exception as e:
        print(f"Error sending transaction for {token_symbol}: {e}")
        return

    # Wait for the transaction receipt
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        if receipt.status == 1:
            print(f"Transaction succeeded in block {receipt.blockNumber}.")
        else:
            print("Transaction failed.")
    except Exception as e:
        print(f"Error waiting for receipt: {e}")


# --- MAIN ---


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 transfer.py <TOKEN_SYMBOL> <QUANTITY>")
        sys.exit(1)

    token_symbol = sys.argv[1]
    token_quantity = float(sys.argv[2])
    token = find_token_by_symbol(token_symbol)
    if token is None:
        print(f"Token with symbol '{token_symbol}' not found in token.yml.")
        sys.exit(1)

    transfer_token(token, token_quantity)


if __name__ == "__main__":
    main()
