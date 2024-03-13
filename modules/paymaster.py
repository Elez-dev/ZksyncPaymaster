from dataclasses import dataclass
from eth_typing import HexStr
from web3 import Web3
import json
from enum import Enum
from pathlib import Path
from typing import Optional
import importlib.resources as pkg_resources
import contract_abi


class JsonConfiguration(Enum):
    COMBINED = "combined"
    STANDARD = "standard"


def paymaster_flow_abi_default():
    global paymaster_flow_abi_cache

    if paymaster_flow_abi_cache is None:
        with pkg_resources.path(contract_abi, "IPaymasterFlow.json") as p:
            with p.open(mode="r") as json_file:
                data = json.load(json_file)
                paymaster_flow_abi_cache = data["abi"]
    return paymaster_flow_abi_cache


class BaseContractEncoder:
    @classmethod
    def from_json(
        cls,
        web3: Web3,
        compiled_contract: Path,
        conf_type: JsonConfiguration = JsonConfiguration.COMBINED,
    ):
        with compiled_contract.open(mode="r") as json_f:
            data = json.load(json_f)
            if conf_type == JsonConfiguration.COMBINED:
                contracts = list()
                for contract_path, contract_data in data["contracts"].items():
                    # Check if 'abi' key exists
                    if "abi" in contract_data and "bin" in contract_data:
                        abi = contract_data["abi"]
                        bin = contract_data["bin"]
                        contracts.append(cls(web3, abi=abi, bytecode=bin))

                return contracts
            else:
                return cls(web3, abi=data["abi"], bytecode=data["bytecode"])

    def __init__(self, web3: Web3, abi, bytecode: Optional[bytes] = None):
        self.web3 = web3
        self.abi = abi
        if bytecode is None:
            self.instance_contract = self.web3.eth.contract(abi=self.abi)
        else:
            self.instance_contract = self.web3.eth.contract(
                abi=self.abi, bytecode=bytecode
            )

    def encode_method(self, fn_name, args: tuple) -> HexStr:
        return self.instance_contract.encodeABI(fn_name, args)

    @property
    def contract(self):
        return self.instance_contract


@dataclass
class PaymasterParams(dict):
    paymaster: HexStr
    paymaster_input: bytes


paymaster_flow_abi_cache = None


class PaymasterFlowEncoder(BaseContractEncoder):
    def __init__(self, web3: Web3):
        super(PaymasterFlowEncoder, self).__init__(
            web3, abi=paymaster_flow_abi_default()
        )

    def encode_approval_based(
        self, address: HexStr, min_allowance: int, inner_input: bytes
    ) -> HexStr:
        return self.encode_method(
            fn_name="approvalBased", args=(address, min_allowance, inner_input)
        )

    def encode_general(self, inputs: bytes) -> HexStr:
        return self.encode_method(fn_name="general", args=tuple([inputs]))
