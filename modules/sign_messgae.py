from eth_account.datastructures import SignedMessage
from eth_account.signers.base import BaseAccount
from eth_typing import ChecksumAddress, HexStr
from eth_utils import keccak
from eth_account.messages import encode_defunct, SignableMessage
from abc import abstractmethod
from modules.eip712struct import EIP712Struct, Address, Uint, Bytes, String
import web3


def make_domain(
    name=None, version=None, chainId=None, verifyingContract=None, salt=None
):
    """Helper method to create the standard EIP712Domain struct for you.

    Per the standard, if a value is not used then the parameter is omitted from the struct entirely.
    """

    if all(i is None for i in [name, version, chainId, verifyingContract, salt]):
        raise ValueError("At least one argument must be given.")

    class EIP712Domain(EIP712Struct):
        pass

    kwargs = dict()
    if name is not None:
        EIP712Domain.name = String()
        kwargs["name"] = str(name)
    if version is not None:
        EIP712Domain.version = String()
        kwargs["version"] = str(version)
    if chainId is not None:
        EIP712Domain.chainId = Uint(256)
        kwargs["chainId"] = int(chainId)
    if verifyingContract is not None:
        EIP712Domain.verifyingContract = Address()
        kwargs["verifyingContract"] = verifyingContract
    if salt is not None:
        EIP712Domain.salt = Bytes(32)
        kwargs["salt"] = salt

    return EIP712Domain(**kwargs)


class EthSignerBase:
    @abstractmethod
    def sign_typed_data(self, typed_data: EIP712Struct, domain=None) -> SignedMessage:
        raise NotImplemented

    @abstractmethod
    def verify_typed_data(self, sig: HexStr, typed_data: EIP712Struct) -> bool:
        raise NotImplemented


class PrivateKeyEthSigner(EthSignerBase):
    _NAME = "zkSync"
    _VERSION = "2"

    def __init__(self, creds: BaseAccount, chain_id: int):
        self.credentials = creds
        self.chain_id = chain_id
        self.default_domain = make_domain(
            name=self._NAME, version=self._VERSION, chainId=self.chain_id
        )

    @property
    def address(self) -> ChecksumAddress:
        return self.credentials.address

    @property
    def domain(self):
        return self.default_domain

    def typed_data_to_signed_bytes(
        self, typed_data: EIP712Struct, domain=None
    ) -> SignableMessage:
        d = domain
        if d is None:
            d = self.domain
        msg = typed_data.signable_bytes(d)
        return encode_defunct(msg)

    def sign_typed_data(self, typed_data: EIP712Struct, domain=None) -> SignedMessage:
        singable_message = self.typed_data_to_signed_bytes(typed_data, domain)
        msg_hash = keccak(singable_message.body)
        return self.credentials.signHash(msg_hash)

    def verify_typed_data(
        self, sig: HexStr, typed_data: EIP712Struct, domain=None
    ) -> bool:
        singable_message = self.typed_data_to_signed_bytes(typed_data, domain)
        msg_hash = keccak(singable_message.body)
        address = web3.Account._recover_hash(message_hash=msg_hash, signature=sig)
        return address.lower() == self.address.lower()
