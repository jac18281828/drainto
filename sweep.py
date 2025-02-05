#!/usr/bin/env python3
import os
import sys
import yaml
import json
import time
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

# Enable HD wallet features (this is an unaudited feature from eth-account)
Account.enable_unaudited_hdwallet_features()

# --- CONFIGURATION ---

# Load environment variables from .env
load_dotenv()

DEST_WALLET = os.getenv("DEST_WALLET")
RPC_URL = os.getenv("RPC_URL")
MNEMONIC = os.getenv("MNEMONIC").strip()

if not DEST_WALLET or not RPC_URL or not MNEMONIC:
    raise Exception("Please ensure DEST_WALLET, RPC_URL, and MNEMONIC are set in the .env file.")

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

# --- SETUP WEB3 & ACCOUNT ---

# Connect to the RPC endpoint
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    raise Exception("Failed to connect to the RPC endpoint.")

chain_id = w3.eth.chain_id

# Derive the account from the mnemonic using the default derivation path for Ethereum (m/44'/60'/0'/0/0)
account = Account.from_mnemonic(MNEMONIC)
my_address = account.address
print(f"Using account: {my_address}")

# --- TOKEN DRAIN FUNCTION ---

def drain_token(token):
    token_name = token.get("name", "Unknown Token")
    token_symbol = token.get("symbol", "")
    token_address = token.get("address")
    decimals = token.get("decimals", 18)

    if not token_address:
        print(f"Token {token_name} has no address defined. Skipping.")
        return

    print(f"\nProcessing {token_name} ({token_symbol}) at address {token_address}")

    # Instantiate token contract
    contract = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)

    try:
        # Get token balance for our account
        balance = contract.functions.balanceOf(my_address).call()
    except Exception as e:
        print(f"Error fetching balance for {token_symbol}: {e}")
        return

    human_balance = balance / (10 ** decimals)
    print(f"Balance: {human_balance} {token_symbol}")

    if balance == 0:
        print(f"No balance for {token_symbol}. Skipping transfer.")
        return

    # Build transaction to transfer entire balance to the destination wallet.
    try:
        nonce = w3.eth.get_transaction_count(my_address)
        gas_price = w3.eth.gas_price

        # Build transaction dictionary; note that gas is estimated from the transfer call.
        tx = contract.functions.transfer(
            Web3.toChecksumAddress(DEST_WALLET), balance
        ).buildTransaction({
            "from": my_address,
            "nonce": nonce,
            "gasPrice": gas_price,
            "chainId": chain_id,
        })

        # Optionally, estimate gas if desired:
        estimated_gas = w3.eth.estimate_gas(tx)
        tx["gas"] = estimated_gas

        print(f"Sending {human_balance} {token_symbol} to {DEST_WALLET}")
        print(f"Transaction details: nonce={nonce}, gas={estimated_gas}, gasPrice={gas_price}")
    except Exception as e:
        print(f"Error building transaction for {token_symbol}: {e}")
        return

    # Sign the transaction
    try:
        signed_tx = account.sign_transaction(tx)
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

    # Optionally, wait for the transaction receipt
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        if receipt.status == 1:
            print(f"Transaction succeeded in block {receipt.blockNumber}.")
        else:
            print("Transaction failed.")
    except Exception as e:
        print(f"Error waiting for receipt: {e}")
        
        
# drain eth to dest wallet
def drain_eth(force: bool = False):
    # Get the current balance of the account
    balance = w3.eth.get_balance(my_address)
    human_balance = w3.from_wei(balance, "ether")
    print(f"ETH Balance: {human_balance} ETH")

    if balance == 0 or human_balance < 1 and not force:
        print("Insufficient balance for ETH. Skipping transfer.")
        return

    # Build transaction to transfer entire balance to the destination wallet.
    try:
        nonce = w3.eth.get_transaction_count(my_address)
        gas_price = w3.eth.gas_price
        
        gas = 21000
        balance_less_gas = balance - (gas * gas_price)

        # Build transaction dictionary
        tx = {
            "to": Web3.to_checksum_address(DEST_WALLET),
            "value": balance_less_gas,
            "gas": gas,
            "gasPrice": gas_price,
            "nonce": nonce,
            "chainId": chain_id,
        }

        print(f"Sending {human_balance} ETH to {DEST_WALLET}")
        print(f"Transaction details: nonce={nonce}, gas=21000, gasPrice={gas_price}")
    except Exception as e:
        print(f"Error building transaction for ETH: {e}")
        return

    # Sign the transaction
    try:
        signed_tx = account.sign_transaction(tx)
    except Exception as e:
        print(f"Error signing transaction for ETH: {e}")
        return

    # Send the transaction
    try:
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"Transaction sent! TX hash: {tx_hash.hex()}")
    except Exception as e:
        print(f"Error sending transaction for ETH: {e}")
        return

    # Optionally, wait for the transaction receipt
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
    print(f"Draining tokens from {my_address} to {DEST_WALLET}...")
    for token in tokens:
        drain_token(token)
        # Pause briefly between transactions to avoid nonce issues
        time.sleep(0.5)
        
    if len(sys.argv) > 1 and sys.argv[1] == "force":
        drain_eth(force=True)
    else:
        drain_eth()

if __name__ == "__main__":
    main()