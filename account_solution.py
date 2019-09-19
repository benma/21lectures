# Needed imports
# In your VM, run `pip3 install pywallet` beforehand.
from pprint import pprint
import account_test
import requests
from pywallet.utils import Wallet

# Set up initial config. The account xpub must be a testnet xpub.

# It is at the level of a bip44 account, so starting at for example m/44'/0'/0'.

# `xpub/0/<index>` and `xpub/1/<index>` will enumerate the receive and change addresses.

xpub_str = "tpubDDjcecUiJegnYexfPHbxVsmsrqoGUeQr6DdU7Apz8Qg56GcThfgcZBdyTR7Ax7xRPLbJX7qS98zkgmvrMfNPhxLfax3KkGtAeV98EJPsbF9"
gap_limit = 20

xpub = Wallet.deserialize(xpub_str, "bitcoin_testnet")
# An account consists of two address chains, the receive and the change addresses.
# account xpub (e.g. m/44'/0'/0'), with addresses living under xpub/<change>/<address>
receive_xpub = xpub.get_child(0)
change_xpub = xpub.get_child(1)


def get_address(xpub):
    """
    Determines the account type. By default p2pkh addresses are generated.
    """
    return xpub.to_address() # p2pkh
# Example:
print(get_address(receive_xpub.get_child(0)))

def get_tx(tx_id):
    return requests.get("https://blockstream.info/testnet/api/tx/{}".format(tx_id)).json()
# Example:
pprint(get_tx("15a78cb63ab3e314a5357166dafc8c53499dc09d06e4fcf1909c618656f4a8e6"))

def get_history(address):
    """
    This returns the list of transaction IDs of all transactions that touch this address.
    This functionality is commonly provided by blockchain indexers, like ElectrumX/Electrs,
    libbitcoin, block explorers, etc.
    Example result:
    ['22bbac62c1f089a0a9c6e5d5c8ca03884e984dec43ac6e4f86f7346f9971656b',
    '15a78cb63ab3e314a5357166dafc8c53499dc09d06e4fcf1909c618656f4a8e6']
    """
    # Fetches up to 25 transactions, need to chain multiple calls if more are needed.
    # We won't bother now.
    txs = requests.get("https://blockstream.info/testnet/api/address/{}/txs".format(address)).json()
    tx_ids = [tx["txid"] for tx in txs]
    return tx_ids
# Example:
pprint(get_history("mgMeHjSHkCHVhRoict9n3q4cRsbxBAFeH5"))

def scan_until_gaplimit(xpub, gap_limit, get_history):
    """
    xpub:
      key to derive addresses from.
      It will be either receive_xpub or change_xpub.
      the xpub deriving change addresses.
      Derive child keys using `xpub.get_child(index)` and derive
      the corresponding address using `get_address()`.
    gap_limit:
      Stop scanning when there are `gap_limit` consecutive addresses without any history.
    get_history:
      same as the function implemented above, use it to fetch the
      address history (transaction IDs).
    Return:
      List of (address, address history) tuples, like:
      [("address1", ["tx id 1", "tx id 2", ...]), ...]
    """
    gap_count = 0
    index = 0
    result = []
    while True:
        address_xpub = xpub.get_child(index)
        address = get_address(address_xpub)

        print("fetching history of address {}: {}".format(index, address))
        result.append((address, get_history(address)))

        # Check if the tail of size gap limit is empty.
        # If so, we have reached the gap limit and can stop scanning.
        if len(result) >= gap_limit:
            tail = result[-gap_limit:]
            if not any([history for _, history in tail]):
                break

        index += 1

    return result

# Performs some basic unit testing to check your implementation.
account_test.test_scan_until_gaplimit(scan_until_gaplimit)

# Scan both address chains until the gap limit is reached, returning the list of addresses and txIDs
# touching them.
receive_histories = scan_until_gaplimit(receive_xpub, gap_limit, get_history)
change_histories = scan_until_gaplimit(change_xpub, gap_limit, get_history)

# Merge into one so we can process all at once going forward.
histories = receive_histories + change_histories

# Gather all addresses belonging to our account for easy lookup
# `"<address>" in account_addresses` checks for existence of an address in our account.
account_addresses = set(address for address, _ in histories)

# Fetch all transactions. A full-fledged wallet needs a local copy of all of them to:
# a) derive the tx ID and verify the merkle inclusion proof (the tx was mined)
# b) show the transaction in a transactions overview screen

print("fetching transactions...")
transactions = {}
for address, history in histories:
    for tx_id in history:
        if tx_id not in transactions:
            transactions[tx_id] = get_tx(tx_id)
            # Skipped: verify that the tx contents derive the same tx ID
            # Skipped: verify that the tx ID is included in the header merkle tree.
print("fetched {} transactions touching {} addresses".format(len(transactions), len(histories)))

if transactions:
    pprint("Example (1st transaction):\n")
    pprint(list(transactions.values())[0])

# The "easy" way to compute an address balance is to ask the remote blockchain index
# for the relevant UTXOs (unspent outputs, e.g. via /api/<address>/utxo) and sum them up.
# A full fledged wallet however builds a local index of the spent and unspent outputs
# from the downloaded transactions, because:
# a) needs no addtional, potentially slow, remote calls
# b) to display correct transaction details, we need to know about
#    our spent outputs too, not just the unspent outputs
# So we do that!

def get_our_outputs(account_addresses, transactions):
    """
    Return all transaction outputs which belong to our account, as a dictionary:
    { outputID: output }
    outputID (also called outpoint) is usually identified by "<txid>:<outputIndex>".
    Example result:
    {
      'ac6ab7ee826e0d68408c6186baba5f78657325997783d784de7e18d4357b5e43:1': {
         'value': '8716503',
         <other output data, but we only really need the value>,
      },
      ...
    }
    Hint: go through all outputs of all transactions (transaction['vout'])  and record
    the outputs belonging to our account.
    """
    our_outputs = {}

    for tx_id, tx in transactions.items():
        output_index = 0
        for tx_output in tx["vout"]:
            if tx_output["scriptpubkey_address"] in account_addresses:
                outpoint = "{}:{}".format(tx_id, output_index)
                our_outputs[outpoint] = tx_output
            output_index += 1

    return our_outputs

our_outputs = get_our_outputs(account_addresses, transactions)
print("found {} outputs belonging to this account".format(len(our_outputs)))

def filter_unspent_outputs(our_outputs, transactions):
    """
    Return the same kind of dictionary as our_outputs, but containing only unspent outputs.
    Hint 1: start with all outputs. Remove spent outputs, leaving only unspent outputs.
    Hint 2: an output is spent if there is an input referencing it.
    """

    unspent_outputs = our_outputs.copy()
    for tx_id, tx in transactions.items():
        tx_inputs = tx["vin"]
        for tx_input in tx_inputs:
            # ID of output spent by this input.
            spent_outpoint = "{}:{}".format(tx_input["txid"], tx_input["vout"])
            if spent_outpoint in our_outputs:
                del unspent_outputs[spent_outpoint]
    return unspent_outputs

unspent_outputs = filter_unspent_outputs(our_outputs, transactions)
print("found {} unspent outputs belonging to this account".format(len(unspent_outputs)))

def get_account_balance(unspent_outputs):
    """
    Finally, return the sum of the unspent output values to get the account balance.
    """
    return sum(output["value"] for output in unspent_outputs.values())

balance = get_account_balance(unspent_outputs)
print("account balance: {} Satoshi".format(balance))
