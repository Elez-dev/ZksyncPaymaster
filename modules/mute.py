import random
from web3 import Web3
import json as js
from settings import SLIPPAGE, VALUE_PRESCALE_SWAP
from loguru import logger
from modules.wallet import Wallet
from modules.paymaster import PaymasterParams, PaymasterFlowEncoder
from modules.func import TxFunctionCall, HexStr, sleeping
from modules.retry import exception_handler
import time

TOKEN = [
    {
        'name': 'USDC',
        'decimal': 6,
        'address': Web3.to_checksum_address('0x3355df6D4c9C3035724Fd0e3914dE96A5a83aaf4'),
    },

    {
        'name': 'USDT',
        'decimal': 6,
        'address': Web3.to_checksum_address('0x493257fd37edb34451f62edf8d2a0c418852ba4c'),
    }
]


class Mute(Wallet):

    """  """

    def __init__(self, private_key, number):
        super().__init__(private_key, number)
        self.address = Web3.to_checksum_address('0x8B791913eB07C32779a16750e3868aA8495F5964')
        self.abi = js.load(open('./abi/mute.txt'))
        self.contract = self.web3.eth.contract(address=self.address, abi=self.abi)

        self.paymaster_address = Web3.to_checksum_address('0x4ae2ba9a5c653038c6d2f5d9f80b28011a454597')

    def get_out_data(self, from_token_address: str, to_token_address: str, amount_in_wei: int):
        min_amount_out, stable_mode, fee = self.contract.functions.getAmountOut(
            amount_in_wei,
            from_token_address,
            to_token_address
        ).call()
        return int(min_amount_out - (min_amount_out / 100 * SLIPPAGE)), stable_mode, fee

    def approve(self, token_to_approve):
        token_contract = self.web3.eth.contract(token_to_approve['address'], abi=self.token_abi)
        max_amount = 2 ** 256 - 1
        dick = {
            'from': self.address_wallet,
            'nonce': self.web3.eth.get_transaction_count(self.address_wallet),
            **self.get_gas_price()
        }
        txn = token_contract.functions.approve(self.address, max_amount).build_transaction(dick)

        token_balance = self.get_token_balance(token_to_approve["address"])
        if token_balance < self.to_wei(token_to_approve["decimal"], 2):
            self.send_transaction_and_wait(txn, f'Mute approve {token_to_approve["name"]}')
        else:
            paymaster_params = PaymasterParams(**{
                "paymaster": Web3.to_checksum_address(self.paymaster_address),
                "paymaster_input": self.web3.to_bytes(hexstr=PaymasterFlowEncoder(self.web3).encode_approval_based(token_to_approve['address'], 2**256-1, b''))
            })

            tx_func_call = TxFunctionCall(
                chain_id=self.web3.eth.chain_id,
                nonce=self.web3.eth.get_transaction_count(self.address_wallet),
                from_=self.address_wallet,
                to=token_to_approve['address'],
                data=HexStr(txn['data']),
                gas_limit=0,
                gas_price=self.web3.eth.gas_price,
                max_priority_fee_per_gas=0,
                gas_per_pub_data=50_000,
                paymaster_params=paymaster_params
            )
            tx_712 = tx_func_call.tx712(txn['gas'])

            self.send_transaction_712_and_wait(tx_712, f'Paymaster Mute.io approve {token_to_approve["name"]}')

    @exception_handler(lable='Buy token Mute')
    def buy_token(self):
        token_to_buy = random.choice(TOKEN)
        logger.info(f'Buy {token_to_buy["name"]} token on MuteSwap')
        balance = self.get_native_balance()
        if balance < Web3.to_wei(0.0005, 'ether'):
            logger.error('Balance < 0.0005 ETH\n')
            return False

        prescale = random.uniform(VALUE_PRESCALE_SWAP[0], VALUE_PRESCALE_SWAP[1])
        value_from_vei = round(Web3.from_wei(balance * prescale, 'ether'), VALUE_PRESCALE_SWAP[2])
        amount_in_wei = Web3.to_wei(value_from_vei, 'ether')

        min_amount_out, stable_mode, _ = self.get_out_data(self.eth_address, token_to_buy['address'], amount_in_wei)

        txn = self.contract.functions.swapExactETHForTokens(
            min_amount_out,
            [self.eth_address, token_to_buy['address']],
            self.address_wallet,
            (int(time.time()) + 10000),
            [stable_mode]
        ).build_transaction({
            'from': self.address_wallet,
            'value': amount_in_wei,
            'gasPrice': self.web3.eth.gas_price,
            'nonce': self.web3.eth.get_transaction_count(self.address_wallet),
        })

        token_balance = self.get_token_balance(token_to_buy['address'])
        if token_balance < self.to_wei(token_to_buy['decimal'], 3):
            self.send_transaction_and_wait(txn, f'Buy {self.from_wei(token_to_buy["decimal"], min_amount_out)} {token_to_buy["name"]} on Mute.io')
            return token_to_buy
        else:
            paymaster_params = PaymasterParams(**{
                "paymaster": Web3.to_checksum_address(self.paymaster_address),
                "paymaster_input": self.web3.to_bytes(hexstr=PaymasterFlowEncoder(self.web3).encode_approval_based(token_to_buy["address"], 2**256-1, b''))
            })

            tx_func_call = TxFunctionCall(
                chain_id=self.web3.eth.chain_id,
                nonce=txn['nonce'],
                from_=self.address_wallet,
                to=txn['to'],
                value=txn['value'],
                data=HexStr(txn['data']),
                gas_limit=0,
                gas_price=self.web3.eth.gas_price,
                max_priority_fee_per_gas=0,
                gas_per_pub_data=50_000,
                paymaster_params=paymaster_params
            )
            tx_712 = tx_func_call.tx712(txn['gas'])

            self.send_transaction_712_and_wait(tx_712, f'Paymaster buy {self.from_wei(token_to_buy["decimal"], min_amount_out)} {token_to_buy["name"]} Mute.io')
            return token_to_buy

    @exception_handler(lable='Sold token Mute')
    def sold_token(self, token_to_sold):

        token_contract = self.web3.eth.contract(token_to_sold['address'], abi=self.token_abi)
        allowance = token_contract.functions.allowance(self.address_wallet, self.address).call()
        if allowance < self.to_wei(token_to_sold["decimal"], 100000):
            self.approve(token_to_sold)
            sleeping(50, 70)

        balance_token = self.get_token_balance(token_to_sold['address']) - self.to_wei(token_to_sold['decimal'], 3)
        if balance_token <= 0:
            return logger.error(f'Token balance < 3 {token_to_sold["name"]}\n')

        min_amount_out, stable_mode, _ = self.get_out_data(token_to_sold['address'], self.eth_address, balance_token)

        txn = self.contract.functions.swapExactTokensForETH(
            balance_token,
            min_amount_out,
            [token_to_sold['address'], self.eth_address],
            self.address_wallet,
            (int(time.time()) + 10000),
            [stable_mode]
        ).build_transaction({
            'from': self.address_wallet,
            'gasPrice': self.web3.eth.gas_price,
            'nonce': self.web3.eth.get_transaction_count(self.address_wallet),
        })

        paymaster_params = PaymasterParams(**{
            "paymaster": Web3.to_checksum_address(self.paymaster_address),
            "paymaster_input": self.web3.to_bytes(hexstr=PaymasterFlowEncoder(self.web3).encode_approval_based(token_to_sold['address'], 2**256-1, b''))

        })

        tx_func_call = TxFunctionCall(
            chain_id=self.web3.eth.chain_id,
            nonce=txn['nonce'],
            from_=self.address_wallet,
            to=txn['to'],
            data=HexStr(txn['data']),
            gas_limit=0,  # Unknown at this state, estimation is done in next step
            gas_price=self.web3.eth.gas_price,
            max_priority_fee_per_gas=0,
            gas_per_pub_data=50_000,
            paymaster_params=paymaster_params
        )
        tx_712 = tx_func_call.tx712(txn['gas'])

        self.send_transaction_712_and_wait(tx_712, f'Paymaster sold {self.from_wei(token_to_sold["decimal"], balance_token)} {token_to_sold["name"]} Mute.io')

