from msoffcrypto.exceptions import DecryptionError, InvalidKeyError
from loguru import logger
from settings import EXCEL_PASSWORD, SHUFFLE_WALLETS
from tqdm import tqdm
from web3 import Web3
from typing import Union
from eth_typing import ChecksumAddress, HexStr
from eth_account.datastructures import SignedMessage
from rlp.sedes import big_endian_int, binary
from rlp.sedes import List as rlpList
from eth_utils import remove_0x_prefix
from dataclasses import dataclass
from modules.eip712struct import EIP712Struct, Address, Uint, Bytes, Array
from typing import List, Optional
from web3.types import AccessList, Nonce
from hashlib import sha256
from web3._utils.compat import TypedDict
import msoffcrypto
import pandas as pd
import random
import time
import io
import sys
import rlp

USDC = {
    'name': 'USDC',
    'decimal': 6,
    'address': Web3.to_checksum_address('0x3355df6D4c9C3035724Fd0e3914dE96A5a83aaf4'),
}


def to_bytes(data: Union[bytes, HexStr]) -> bytes:
    if isinstance(data, bytes):
        return data
    return bytes.fromhex(remove_0x_prefix(data))


def int_to_bytes(x: int) -> bytes:
    return x.to_bytes((x.bit_length() + 7) // 8, byteorder=sys.byteorder)


def encode_address(addr: Union[Address, ChecksumAddress, str]) -> bytes:
    if len(addr) == 0:
        return bytes()
    if isinstance(addr, bytes):
        return addr
    return bytes.fromhex(remove_0x_prefix(addr))


def hash_byte_code(bytecode: bytes) -> bytes:
    bytecode_len = len(bytecode)
    bytecode_size = int(bytecode_len / 32)
    if bytecode_len % 32 != 0:
        raise RuntimeError("Bytecode length in 32-byte words must be odd")
    if bytecode_size > 2**16:
        raise OverflowError("hash_byte_code, bytecode length must be less than 2^16")
    bytecode_hash = sha256(bytecode).digest()
    encoded_len = bytecode_size.to_bytes(2, byteorder="big")
    ret = b"\x01\00" + encoded_len + bytecode_hash[4:]
    return ret


DynamicBytes = Bytes(0)


@dataclass
class PaymasterParams(dict):
    paymaster: HexStr
    paymaster_input: bytes


@dataclass
class EIP712Meta:
    # GAS_PER_PUB_DATA_DEFAULT = 16 * 10000
    # GAS_PER_PUB_DATA_DEFAULT = 20 * 10000
    GAS_PER_PUB_DATA_DEFAULT = 50000

    gas_per_pub_data: int = GAS_PER_PUB_DATA_DEFAULT
    custom_signature: Optional[bytes] = None
    factory_deps: Optional[List[bytes]] = None
    paymaster_params: Optional[PaymasterParams] = None


@dataclass
class Transaction712:
    EIP_712_TX_TYPE = 113

    chain_id: int
    nonce: Nonce
    gas_limit: int
    to: Union[Address, ChecksumAddress, str]
    value: int
    data: Union[bytes, HexStr]
    maxPriorityFeePerGas: int
    maxFeePerGas: int
    from_: Union[bytes, HexStr]
    meta: EIP712Meta

    def encode(self, signature: Optional[SignedMessage] = None) -> bytes:
        factory_deps_data = []
        factory_deps_elements = None
        factory_deps = self.meta.factory_deps
        if factory_deps is not None and len(factory_deps) > 0:
            factory_deps_data = factory_deps
            factory_deps_elements = [binary for _ in range(len(factory_deps_data))]

        paymaster_params_data = []
        paymaster_params_elements = None
        paymaster_params = self.meta.paymaster_params
        if (
            paymaster_params is not None
            and paymaster_params.paymaster is not None
            and paymaster_params.paymaster_input is not None
        ):
            paymaster_params_data = [
                bytes.fromhex(remove_0x_prefix(paymaster_params.paymaster)),
                paymaster_params.paymaster_input,
            ]
            paymaster_params_elements = [binary, binary]

        class InternalRepresentation(rlp.Serializable):
            fields = [
                ("nonce", big_endian_int),
                ("maxPriorityFeePerGas", big_endian_int),
                ("maxFeePerGas", big_endian_int),
                ("gasLimit", big_endian_int),
                ("to", binary),
                ("value", big_endian_int),
                ("data", binary),
                ("chain_id", big_endian_int),
                ("unknown1", binary),
                ("unknown2", binary),
                ("chain_id2", big_endian_int),
                ("from", binary),
                ("gasPerPubdata", big_endian_int),
                ("factoryDeps", rlpList(elements=factory_deps_elements, strict=False)),
                ("signature", binary),
                (
                    "paymaster_params",
                    rlpList(elements=paymaster_params_elements, strict=True),
                ),
            ]

        custom_signature = self.meta.custom_signature
        if custom_signature is not None:
            rlp_signature = custom_signature
        elif signature is not None:
            rlp_signature = signature.signature
        else:
            raise RuntimeError("Custom signature and signature can't be None both")

        representation_params = {
            "nonce": self.nonce,
            "maxPriorityFeePerGas": self.maxPriorityFeePerGas,
            "maxFeePerGas": self.maxFeePerGas,
            "gasLimit": self.gas_limit,
            "to": encode_address(self.to),
            "value": self.value,
            "data": to_bytes(self.data),
            "chain_id": self.chain_id,
            "unknown1": b"",
            "unknown2": b"",
            "chain_id2": self.chain_id,
            "from": encode_address(self.from_),
            "gasPerPubdata": self.meta.gas_per_pub_data,
            "factoryDeps": factory_deps_data,
            "signature": rlp_signature,
            "paymaster_params": paymaster_params_data,
        }
        representation = InternalRepresentation(**representation_params)
        encoded_rlp = rlp.encode(representation, infer_serializer=True, cache=False)
        return int_to_bytes(self.EIP_712_TX_TYPE) + encoded_rlp

    def to_eip712_struct(self) -> EIP712Struct:
        class Transaction(EIP712Struct):
            pass

        paymaster: int = 0
        paymaster_params = self.meta.paymaster_params
        if paymaster_params is not None and paymaster_params.paymaster is not None:
            paymaster = int(paymaster_params.paymaster, 16)

        data = to_bytes(self.data)

        factory_deps = self.meta.factory_deps
        factory_deps_hashes = b""
        if factory_deps is not None and len(factory_deps):
            factory_deps_hashes = tuple(
                [hash_byte_code(bytecode) for bytecode in factory_deps]
            )

        setattr(Transaction, "txType", Uint(256))
        setattr(Transaction, "from", Uint(256))
        setattr(Transaction, "to", Uint(256))
        setattr(Transaction, "gasLimit", Uint(256))
        setattr(Transaction, "gasPerPubdataByteLimit", Uint(256))
        setattr(Transaction, "maxFeePerGas", Uint(256))
        setattr(Transaction, "maxPriorityFeePerGas", Uint(256))
        setattr(Transaction, "paymaster", Uint(256))
        setattr(Transaction, "nonce", Uint(256))
        setattr(Transaction, "value", Uint(256))
        setattr(Transaction, "data", DynamicBytes)
        setattr(Transaction, "factoryDeps", Array(Bytes(32)))
        setattr(Transaction, "paymasterInput", DynamicBytes)

        paymaster_input = b""
        if (
            paymaster_params is not None
            and paymaster_params.paymaster_input is not None
        ):
            paymaster_input = paymaster_params.paymaster_input

        kwargs = {
            "txType": self.EIP_712_TX_TYPE,
            "from": int(self.from_, 16),
            "to": int(self.to, 16),
            "gasLimit": self.gas_limit,
            "gasPerPubdataByteLimit": self.meta.gas_per_pub_data,
            "maxFeePerGas": self.maxFeePerGas,
            "maxPriorityFeePerGas": self.maxPriorityFeePerGas,
            "paymaster": paymaster,
            "nonce": self.nonce,
            "value": self.value,
            "data": data,
            "factoryDeps": factory_deps_hashes,
            "paymasterInput": paymaster_input,
        }
        return Transaction(**kwargs)


Transaction = TypedDict(
    "Transaction",
    {
        "chain_id": int,
        "nonce": int,
        "from": HexStr,
        "to": HexStr,
        "gas": int,
        "gasPrice": int,
        "maxPriorityFeePerGas": int,
        "value": int,
        "data": HexStr,
        "transactionType": int,
        "accessList": Optional[AccessList],
        "eip712Meta": EIP712Meta,
    },
    total=False,
)


class TxBase:
    def __init__(self, trans: Transaction):
        self.tx_: Transaction = trans

    @property
    def tx(self) -> Transaction:
        return self.tx_

    def tx712(self, estimated_gas: int) -> Transaction712:
        return Transaction712(
            chain_id=self.tx["chain_id"],
            nonce=Nonce(self.tx["nonce"]),
            gas_limit=estimated_gas,
            to=self.tx["to"],
            value=self.tx["value"],
            data=self.tx["data"],
            maxPriorityFeePerGas=self.tx["maxPriorityFeePerGas"],
            maxFeePerGas=self.tx["gasPrice"],
            from_=self.tx["from"],
            meta=self.tx["eip712Meta"],
        )


class TxFunctionCall(TxBase):
    def __init__(
        self,
        from_: HexStr,
        to: HexStr,
        value: int = 0,
        chain_id: int = None,
        nonce: int = None,
        data: HexStr = HexStr("0x"),
        gas_limit: int = 0,
        gas_price: int = 0,
        max_priority_fee_per_gas: int = 100_000_000,
        paymaster_params=None,
        custom_signature=None,
        gas_per_pub_data: int = EIP712Meta.GAS_PER_PUB_DATA_DEFAULT,
    ):
        eip712_meta = EIP712Meta(
            gas_per_pub_data=gas_per_pub_data,
            custom_signature=custom_signature,
            factory_deps=None,
            paymaster_params=paymaster_params,
        )

        super(TxFunctionCall, self).__init__(
            trans={
                "chain_id": chain_id,
                "nonce": nonce,
                "from": from_,
                "to": to,
                "gas": gas_limit,
                "gasPrice": gas_price,
                "maxPriorityFeePerGas": max_priority_fee_per_gas,
                "value": value,
                "data": data,
                "transactionType": 113,
                "eip712Meta": eip712_meta,
            }
        )


def shuffle(wallets_list):
    if SHUFFLE_WALLETS is True:
        numbered_wallets = list(enumerate(wallets_list, start=1))
        random.shuffle(numbered_wallets)
    elif SHUFFLE_WALLETS is False:
        numbered_wallets = list(enumerate(wallets_list, start=1))
    else:
        raise ValueError("\nНеверное значение переменной 'shuffle_wallets'. Ожидается 'True' or 'False'.")
    return numbered_wallets


def sleeping(sleep_from: int, sleep_to: int):
    delay = random.randint(sleep_from, sleep_to)
    time.sleep(1)
    with tqdm(
            total=delay,
            desc="💤 Sleep",
            bar_format="{desc}: |{bar:20}| {percentage:.0f}% | {n_fmt}/{total_fmt}",
            colour="green"
    ) as pbar:
        for _ in range(delay):
            time.sleep(1)
            pbar.update(1)
    time.sleep(1)
    print()


def get_accounts_data():
    decrypted_data = io.BytesIO()
    with open('./data/accounts_data.xlsx', 'rb') as file:
        if EXCEL_PASSWORD:
            time.sleep(1)
            password = input('Enter the password: ')
            office_file = msoffcrypto.OfficeFile(file)

            try:
                office_file.load_key(password=password)
            except msoffcrypto.exceptions.DecryptionError:
                logger.info('\n⚠️ Incorrect password to decrypt Excel file! ⚠️\n')
                raise DecryptionError('Incorrect password')

            try:
                office_file.decrypt(decrypted_data)
            except msoffcrypto.exceptions.InvalidKeyError:
                logger.info('\n⚠️ Incorrect password to decrypt Excel file! ⚠️\n')
                raise InvalidKeyError('Incorrect password')

            except msoffcrypto.exceptions.DecryptionError:
                logger.info('\n⚠️ Set password on your Excel file first! ⚠️\n')
                raise DecryptionError('Excel without password')

            office_file.decrypt(decrypted_data)

            try:
                wb = pd.read_excel(decrypted_data)
            except ValueError as error:
                logger.info('\n⚠️ Wrong page name! ⚠️\n')
                raise ValueError(f"{error}")
        else:
            try:
                wb = pd.read_excel(file)
            except ValueError as error:
                logger.info('\n⚠️ Wrong page name! ⚠️\n')
                raise ValueError(f"{error}")

        accounts_data = {}
        for index, row in wb.iterrows():
            private_key_evm = row["Private Key EVM"]
            accounts_data[int(index) + 1] = {
                "private_key_evm": private_key_evm,
            }

        priv_key_evm = []
        for k, v in accounts_data.items():
            priv_key_evm.append(v['private_key_evm'])
        return priv_key_evm
