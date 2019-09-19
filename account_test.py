from pywallet.utils import Wallet

xpub_str = "tpubDDjcecUiJegnYexfPHbxVsmsrqoGUeQr6DdU7Apz8Qg56GcThfgcZBdyTR7Ax7xRPLbJX7qS98zkgmvrMfNPhxLfax3KkGtAeV98EJPsbF9"
xpub = Wallet.deserialize(xpub_str, "bitcoin_testnet")

def test_scan_until_gaplimit(scan_until_gaplimit):
    addresses = [xpub.get_child(i).to_address() for i in range(20)]
    def get_history(address):
        nonlocal histories
        m = dict(histories)
        assert address in m, "scanning too far?"
        return m[address]

    gap_limit = 5
    empty = [[]]*gap_limit

    histories = list(zip(addresses, empty))
    expected = histories
    result = scan_until_gaplimit(xpub, gap_limit, get_history)
    assert result == expected, "Got {}, expected {}".format(result, expected)

    histories = list(zip(addresses, [["tx1", "tx2"], ["tx1"]] + empty))
    expected = histories
    result = scan_until_gaplimit(xpub, gap_limit, get_history)
    assert result == expected, "Got {}, expected {}".format(result, expected)

    histories = list(zip(addresses,
                    [[]]*(gap_limit - 1) + [["tx1", "tx2"], [], [], ["tx1"], [], ["tx3", "tx4"]] + empty + empty))
    expected = histories[:-gap_limit]
    result = scan_until_gaplimit(xpub, gap_limit, get_history)
    assert result == expected, "Got {}, expected {}".format(result, expected)
    print("scan_until_gaplimit: tests passed!")
