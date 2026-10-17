"""Token metadata and dependency reads must be mainnet-only and block-pinned."""
import copy
import sys
import unittest
from pathlib import Path

from maxpane_dashboard.data.surf_nft_chain import Inspector, selector
from maxpane_dashboard.data.surf_nft_rules.tokens import read_token, refresh_utility_reads, attach_token_metadata

ADDRESS = "0x" + "a" * 40
DEPENDENCY = "0x" + "b" * 40


def word(value):
    return "0x" + format(value, "064x")


class TokenReads(unittest.TestCase):
    def inspector(self, values=None, chain=1, code="0x1234"):
        self.calls = []
        values = values or {"name()": "0x" + b"Token".hex().ljust(64, "0"),
                            "symbol()": "0x" + b"TOK".hex().ljust(64, "0"),
                            "decimals()": word(6), "totalSupply()": word(1234567890123456789)}
        def rpc(chain_id, method, params):
            self.calls.append((chain_id, method, params))
            if method == "eth_chainId":
                return hex(chain)
            if method == "eth_blockNumber":
                return "0xabc"
            if method == "eth_getBlockByNumber":
                return {"number": params[0], "timestamp": "0x69000000"}
            if method == "eth_getCode":
                return code
            if method == "eth_call":
                for signature, result in values.items():
                    if params[0]["data"] == selector(signature):
                        return result
                raise RuntimeError("getter unavailable")
            raise AssertionError(method)
        return Inspector(rpc=rpc)

    def test_metadata_uses_one_verified_block_and_exact_supply(self):
        result = read_token(self.inspector(), 1, ADDRESS)
        self.assertEqual(result["status"], "checked")
        self.assertEqual((result["name"], result["symbol"], result["decimals"]), ("Token", "TOK", 6))
        self.assertEqual(result["totalSupply"], "1234567890123456789")
        self.assertEqual(result["formattedSupply"], "1234567890123.456789")
        for _, method, params in self.calls:
            if method in {"eth_call", "eth_getCode"}:
                self.assertEqual(params[-1], "0xabc")

    def test_optional_metadata_failure_never_defaults_decimals(self):
        result = read_token(self.inspector({"totalSupply()": word(0)}), 1, ADDRESS)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["totalSupply"], "0")
        self.assertIsNone(result["decimals"])
        self.assertIsNone(result["formattedSupply"])

    def test_invalid_decimals_and_no_code_are_explicit(self):
        result = read_token(self.inspector({"decimals()": word(256), "totalSupply()": word(1)}), 1, ADDRESS)
        self.assertIsNone(result["decimals"])
        self.assertTrue(any("decimals" in warning for warning in result["warnings"]))
        result = read_token(self.inspector(code="0x"), 1, ADDRESS)
        self.assertEqual(result["status"], "no-code")
        self.assertFalse(result["codePresent"])
        self.assertFalse(any(method == "eth_call" for _, method, _ in self.calls))

    def test_wrong_chain_or_unsupported_network_never_reads_token(self):
        result = read_token(self.inspector(chain=4663), 1, ADDRESS)
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(any(method == "eth_getCode" for _, method, _ in self.calls))
        inspector = self.inspector()
        with self.assertRaises(ValueError):
            read_token(inspector, 11155111, ADDRESS)
        self.assertEqual(self.calls, [])

    def test_metadata_deduplicates_by_chain_address_and_preserves_role(self):
        inspector = self.inspector()
        token = {"chainId": 1, "address": ADDRESS, "roles": ["payment"], "status": "planned"}
        records = [{"tokens": [copy.deepcopy(token)]}, {"tokens": [copy.deepcopy(token)]}]
        result = attach_token_metadata(records, inspector, workers=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(sum(method == "eth_getCode" for _, method, _ in self.calls), 1)
        self.assertEqual(records[0]["tokens"][0]["status"], "planned")
        self.assertEqual(records[0]["tokens"][0]["onchain"]["symbol"], "TOK")

    def test_offline_missing_cache_and_unknown_address_do_not_probe(self):
        inspector = self.inspector()
        records = [{"tokens": [{"chainId": 1, "address": ADDRESS}, {"chainId": 4663, "address": None}]}]
        attach_token_metadata(records, inspector, offline=True)
        self.assertEqual(self.calls, [])
        self.assertEqual(records[0]["tokens"][0]["onchain"]["status"], "unavailable")
        self.assertEqual(records[0]["tokens"][1]["onchain"]["status"], "unverified-address")

    def test_ordered_dependency_reads_use_resolved_address_and_namespace(self):
        inspector = self.inspector({"registry()": word(int(DEPENDENCY, 16)), "token()": word(int(ADDRESS, 16))})
        chain = {"chainId": 1, "address": ADDRESS, "readBlock": 2748, "reads": {}}
        specs = [{"name": "registry", "type": "address"},
                 {"name": "token", "type": "address", "addressFrom": "registry", "namespace": "GameRegistry"}]
        refresh_utility_reads(chain, inspector, specs)
        self.assertEqual(chain["reads"]["registry"], DEPENDENCY)
        result = chain["dependencyReads"]["GameRegistry"]
        self.assertEqual(result["address"], DEPENDENCY)
        self.assertEqual(result["reads"]["token"], ADDRESS)
        self.assertEqual(result["readBlock"], chain["readBlock"])
        self.assertEqual(self.calls[-1][2][0]["to"], DEPENDENCY)

    def test_failed_dependency_read_removes_stale_value(self):
        inspector = self.inspector({"totalSupply()": word(0)})
        chain = {"chainId": 1, "address": ADDRESS, "readBlock": 2748, "reads": {"registry": DEPENDENCY}}
        refresh_utility_reads(chain, inspector, [{"name": "registry", "type": "address"},
                                               {"name": "token", "type": "address", "addressFrom": "registry", "namespace": "GameRegistry"}])
        self.assertNotIn("registry", chain["reads"])
        self.assertIn("registry", chain["readErrors"])
        self.assertEqual(chain["dependencyReads"]["GameRegistry"]["reads"], {})


if __name__ == "__main__":
    unittest.main()
