from requests.adapters import Retry
import requests
from loguru import logger
from web3 import Web3
from settings import CHAIN_RPC
import time
import json as js
from modules.sign_messgae import PrivateKeyEthSigner
from modules.tg_bot import TgBot


class Wallet(TgBot):

    def __init__(self, private_key, number):
        self.private_key = private_key
        self.number = number
        self.web3 = self.get_web3()
        self.account = self.web3.eth.account.from_key(private_key)
        self.address_wallet = self.account.address
        self.token_abi = js.load(open('./abi/token.txt'))
        self.eth_address = Web3.to_checksum_address('0x5AEa5775959fBC2557Cc8789bC1bf90A239D9a91')
        self.zero_address = '0x0000000000000000000000000000000000000000'

    @staticmethod
    def get_web3():
        retries = Retry(total=10, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = requests.adapters.HTTPAdapter(max_retries=retries)
        session = requests.Session()
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return Web3(Web3.HTTPProvider(CHAIN_RPC['ZkSync'], request_kwargs={'timeout': 60}, session=session))

    @staticmethod
    def to_wei(decimal, amount):
        if decimal == 6:
            unit = 'picoether'
        else:
            unit = 'ether'

        return Web3.to_wei(amount, unit)

    @staticmethod
    def from_wei(decimal, amount):
        if decimal == 6:
            unit = 'picoether'
        elif decimal == 8:
            return float(amount / 10 ** 8)
        else:
            unit = 'ether'

        return Web3.from_wei(amount, unit)

    def send_transaction_and_wait(self, tx, message):

        signed_txn = self.web3.eth.account.sign_transaction(tx, private_key=self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        logger.info('Sent a transaction')
        time.sleep(5)
        tx_receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=900, poll_latency=5)
        if tx_receipt.status == 1:
            logger.success('The transaction was successfully mined')
        else:
            logger.error("Transaction failed, I'm trying again")
            self.send_message_error(self.number, message, self.address_wallet, "Transaction failed, I'm trying again")
            raise ValueError('')

        self.send_message_success(self.number, message, self.address_wallet, f'https://era.zksync.network/tx/{tx_hash.hex()}')
        logger.success(f'[{self.number}] {message} || https://era.zksync.network/tx/{tx_hash.hex()}\n')
        return tx_hash

    def get_native_balance(self):
        return self.web3.eth.get_balance(self.address_wallet)

    def get_token_balance(self, token_address):
        token_contract = self.web3.eth.contract(address=token_address, abi=self.token_abi)
        return token_contract.functions.balanceOf(self.address_wallet).call()

    def get_gas_price(self):
        return {'maxFeePerGas': self.web3.eth.gas_price, 'maxPriorityFeePerGas': 0}

    def check_allowance(self, address, token):
        token_contract = self.web3.eth.contract(address=Web3.to_checksum_address(token), abi=self.token_abi)
        return token_contract.functions.allowance(self.address_wallet, Web3.to_checksum_address(address)).call()

    def send_transaction_712_and_wait(self, tx_712, message):
        signer = PrivateKeyEthSigner(self.account, 324)
        signed_message = signer.sign_typed_data(tx_712.to_eip712_struct())
        msg = tx_712.encode(signed_message)
        tx_hash = self.web3.eth.send_raw_transaction(msg)
        logger.info('Sent a transaction')
        time.sleep(5)
        tx_receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=900, poll_latency=5)
        if tx_receipt.status == 1:
            logger.success('The transaction was successfully mined')
        else:
            logger.error("Transaction failed, I'm trying again")
            self.send_message_error(self.number, message, self.address_wallet, "Transaction failed, I'm trying again")
            raise ValueError('')

        self.send_message_success(self.number, message, self.address_wallet, f'https://era.zksync.network/tx/{tx_hash.hex()}')
        logger.success(f'[{self.number}] {message} || https://era.zksync.network/tx/{tx_hash.hex()}\n')
        return tx_hash
