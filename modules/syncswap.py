import random
from web3 import Web3
from eth_abi import abi
import json as js
import time
from settings import SLIPPAGE, VALUE_PRESCALE_SWAP
from loguru import logger
from modules.wallet import Wallet
from modules.paymaster import PaymasterParams, PaymasterFlowEncoder
from modules.func import TxFunctionCall, HexStr, sleeping
from modules.retry import exception_handler

TOKEN = [
    {
        'name': 'USDC',
        'decimal': 6,
        'address': Web3.to_checksum_address('0x3355df6D4c9C3035724Fd0e3914dE96A5a83aaf4')
    },

    {
        'name': 'USDT',
        'decimal': 6,
        'address': Web3.to_checksum_address('0x493257fd37edb34451f62edf8d2a0c418852ba4c'),
    },

    {
        'name': 'DAI',
        'decimal': 18,
        'address': Web3.to_checksum_address('0x4B9eb6c0b6ea15176BBF62841C6B2A8a398cb656'),
    },
]


class SynkSwap(Wallet):

    """  """

    def __init__(self, private_key, number):
        super().__init__(private_key, number)
        self.classic_pool_address = Web3.to_checksum_address('0xf2DAd89f2788a8CD54625C60b55cD3d2D0ACa7Cb')
        self.classic_pool_factory_abi = js.load(open('./abi/classic_pool_factory_syncswap.txt'))
        self.classic_pool_contract = self.web3.eth.contract(address=self.classic_pool_address, abi=self.classic_pool_factory_abi)

        self.router_address = Web3.to_checksum_address('0x9B5def958d0f3b6955cBEa4D5B7809b2fb26b059')
        self.router_abi = js.load(open('./abi/router_syncswap.txt'))
        self.router_contract = self.web3.eth.contract(address=self.router_address, abi=self.router_abi)

        self.paymaster_address = Web3.to_checksum_address('0x0c08f298A75A090DC4C0BB4CaA4204B8B9D156c1')
        self.classic_pool_abi = js.load(open('./abi/classic_pool_syncswap.txt'))

    def get_min_amount_out(self, pool_address, token_address, amount):
        pool_contract = self.web3.eth.contract(address=pool_address, abi=self.classic_pool_abi)
        min_amount_out = pool_contract.functions.getAmountOut(
            token_address,
            amount,
            self.address_wallet
        ).call()
        return int(min_amount_out - (min_amount_out // 100 * SLIPPAGE))

    def approve(self, token_to_approve):
        token_contract = self.web3.eth.contract(token_to_approve['address'], abi=self.token_abi)
        max_amount = 2 ** 256 - 1
        dick = {
            'from': self.address_wallet,
            'nonce': self.web3.eth.get_transaction_count(self.address_wallet),
            **self.get_gas_price()
        }
        txn = token_contract.functions.approve(self.router_address, max_amount).build_transaction(dick)

        token_balance = self.get_token_balance(token_to_approve["address"])
        if token_balance < self.to_wei(token_to_approve["decimal"], 2):
            self.send_transaction_and_wait(txn, f'Syncswap approve {token_to_approve["name"]}')
        else:
            min_allowance = self.to_wei(token_to_approve["decimal"], 2000)
            inner_input = Web3.to_bytes(abi.encode(['uint64'], [0]))

            paymaster_params = PaymasterParams(**{
                "paymaster": Web3.to_checksum_address(self.paymaster_address),
                "paymaster_input": self.web3.to_bytes(hexstr=PaymasterFlowEncoder(self.web3).encode_approval_based(token_to_approve['address'], min_allowance, inner_input))
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

            self.send_transaction_712_and_wait(tx_712, f'Paymaster Syncswap approve {token_to_approve["name"]}')

    @exception_handler()
    def buy_token(self):
        balance = self.get_native_balance()
        if balance < Web3.to_wei(0.0005, 'ether'):
            logger.error('Balance < 0.0005 ETH\n')
            return False

        token_to_buy = random.choice(TOKEN)

        prescale = random.uniform(VALUE_PRESCALE_SWAP[0], VALUE_PRESCALE_SWAP[1])
        value_from_vei = round(Web3.from_wei(balance * prescale, 'ether'), VALUE_PRESCALE_SWAP[2])
        amount_in_wei = Web3.to_wei(value_from_vei, 'ether')

        pool_address = self.classic_pool_contract.functions.getPool(self.eth_address, token_to_buy['address']).call()

        min_amount_out = self.get_min_amount_out(pool_address, self.eth_address, amount_in_wei)

        swap_data = abi.encode(['address', 'address', 'uint8'], [self.eth_address, self.address_wallet, 1])
        steps = [
            pool_address,
            Web3.to_hex(swap_data),
            self.zero_address,
            '0x',
            True,
        ]

        paths = [
            [steps],
            self.zero_address,
            amount_in_wei
        ]
        deadline = int(time.time()) + 1800
        txn = self.router_contract.functions.swap(
            [paths],
            min_amount_out,
            deadline,
        ).build_transaction({
            'from': self.address_wallet,
            'value': amount_in_wei,
            'nonce': self.web3.eth.get_transaction_count(self.address_wallet),
            **self.get_gas_price()
        })

        token_balance = self.get_token_balance(token_to_buy['address'])
        if token_balance < self.to_wei(token_to_buy['decimal'], 3):
            self.send_transaction_and_wait(txn, f'Buy {self.from_wei(token_to_buy["decimal"], min_amount_out)} {token_to_buy["name"]} on Syncswap')
            return token_to_buy
        else:
            min_allowance = self.to_wei(token_to_buy["decimal"], 2000)
            inner_input = Web3.to_bytes(abi.encode(['uint64'], [0]))

            paymaster_params = PaymasterParams(**{
                "paymaster": Web3.to_checksum_address(self.paymaster_address),
                "paymaster_input": self.web3.to_bytes(
                    hexstr=PaymasterFlowEncoder(self.web3).encode_approval_based(token_to_buy['address'], min_allowance, inner_input))
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

            self.send_transaction_712_and_wait(tx_712, f'Paymaster buy {self.from_wei(token_to_buy["decimal"], min_amount_out)} {token_to_buy["name"]} Syncswap')
            return token_to_buy

    @exception_handler()
    def sold_token(self, token_to_sold):
        token_contract = self.web3.eth.contract(token_to_sold['address'], abi=self.token_abi)
        allowance = token_contract.functions.allowance(self.address_wallet, self.router_address).call()
        if allowance < self.to_wei(token_to_sold["decimal"], 100000):
            self.approve(token_to_sold)
            sleeping(50, 70)

        balance_token = self.get_token_balance(token_to_sold['address']) - self.to_wei(token_to_sold['decimal'], 3)
        if balance_token <= 0:
            return logger.error(f'Token balance < 3 {token_to_sold["name"]}\n')

        pool_address = self.classic_pool_contract.functions.getPool(token_to_sold['address'], self.eth_address).call()

        min_amount_out = self.get_min_amount_out(pool_address, token_to_sold['address'], balance_token)

        swap_data = abi.encode(['address', 'address', 'uint8'], [token_to_sold['address'], self.address_wallet, 1])
        steps = [
            pool_address,
            Web3.to_hex(swap_data),
            self.zero_address,
            '0x',
            True,
        ]

        paths = [
            [steps],
            token_to_sold['address'],
            balance_token
        ]
        deadline = int(time.time()) + 1800
        txn = self.router_contract.functions.swap(
            [paths],
            min_amount_out,
            deadline,
        ).build_transaction({
            'from': self.address_wallet,
            'nonce': self.web3.eth.get_transaction_count(self.address_wallet),
            **self.get_gas_price()
        })

        min_allowance = self.to_wei(token_to_sold['decimal'], 2000)
        inner_input = Web3.to_bytes(abi.encode(['uint64'], [0]))

        paymaster_params = PaymasterParams(**{
            "paymaster": Web3.to_checksum_address(self.paymaster_address),
            "paymaster_input": self.web3.to_bytes(
                hexstr=PaymasterFlowEncoder(self.web3).encode_approval_based(token_to_sold['address'], min_allowance, inner_input))
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

        self.send_transaction_712_and_wait(tx_712, f'Paymaster sold {self.from_wei(token_to_sold["decimal"], balance_token)} {token_to_sold["name"]} Syncswap')
