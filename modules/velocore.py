import random
from web3 import Web3
from eth_abi import abi
import json as js
from eth_utils import to_bytes, to_hex
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
        'address': Web3.to_checksum_address('0x3355df6D4c9C3035724Fd0e3914dE96A5a83aaf4'),
        'pool': Web3.to_checksum_address('0x42D106c4A1d0Bc5C482c11853A3868d807A3781d')
    },

    {
        'name': 'USDT',
        'decimal': 6,
        'address': Web3.to_checksum_address('0x493257fd37edb34451f62edf8d2a0c418852ba4c'),
        'pool': Web3.to_checksum_address('0xF0e86a60Ae7e9bC0F1e59cAf3CC56f434b3024c0')
    }

    # {
    #     'name': 'DAI',
    #     'decimal': 18,
    #     'address': Web3.to_checksum_address('0x4B9eb6c0b6ea15176BBF62841C6B2A8a398cb656'),
    #     'pool': Web3.to_checksum_address('0x8eB36AE0CD568A884DAD95433b63f8A5db7682a7')
    # },
]


class Velocore(Wallet):

    """  """

    def __init__(self, private_key, number):
        super().__init__(private_key, number)
        self.multicall_address = Web3.to_checksum_address('0xF9cda624FBC7e059355ce98a31693d299FACd963')
        self.multicall_abi = js.load(open('./abi/velocore_multicall.txt'))
        self.multicall_contract = self.web3.eth.contract(address=self.multicall_address, abi=self.multicall_abi)

        self.router_address = Web3.to_checksum_address('0xf5E67261CB357eDb6C7719fEFAFaaB280cB5E2A6')
        self.router_abi = js.load(open('./abi/velocore_router.txt'))
        self.router_contract = self.web3.eth.contract(address=self.router_address, abi=self.router_abi)

        self.paymaster_address = Web3.to_checksum_address('0x443F985fd3484b9FDC7B5df58c9A0FAdbe449b92')

    @staticmethod
    def to_token_info(token_ref_index: int, method: int, min_amount_out:int = 0) -> str:
        encode_amount = 2 ** 127 - 1 - min_amount_out
        return to_bytes(token_ref_index) + to_bytes(method) + abi.encode(['uint128'], [encode_amount])[2:]

    def get_min_amount_out(self, from_token_address, to_token_address, reverse_flag, pool_address, amounts):
        at_most = 1
        _all = 2
        eth_mask = '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'

        data = self.multicall_contract.functions.aggregate3(
            [
                (
                    self.router_address,
                    True,
                    to_bytes(hexstr=self.router_contract.encodeABI(
                        fn_name='query',
                        args=(
                            self.address_wallet,
                            [
                                abi.encode(['address'], [to_token_address if reverse_flag else from_token_address]),
                                eth_mask,
                            ],
                            amounts,
                            [
                                [
                                    abi.encode(['address'], [pool_address]),
                                    [
                                        self.to_token_info(0x00, at_most if reverse_flag else _all),
                                        self.to_token_info(0x01, _all if reverse_flag else at_most),
                                    ],
                                    '0x00'
                                ]
                            ]
                        )
                    )
                    )
                )
            ]
        ).call()
        hex_data = to_hex(data[0][1])
        token_amount_hex = hex_data[-128:-64] if reverse_flag else hex_data[-64:]

        min_amount_out = int(token_amount_hex, 16)

        return int(min_amount_out - (min_amount_out / 100 * SLIPPAGE))

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
            self.send_transaction_and_wait(txn, f'Velocore approve {token_to_approve["name"]}')
        else:
            if token_to_approve['name'] == 'DAI':
                min_allowance = 696493865665783254
            else:
                min_allowance = 1436595
            paymaster_params = PaymasterParams(**{
                "paymaster": Web3.to_checksum_address(self.paymaster_address),
                "paymaster_input": self.web3.to_bytes(hexstr=PaymasterFlowEncoder(self.web3).encode_approval_based(token_to_approve['address'], min_allowance, b''))
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

            self.send_transaction_712_and_wait(tx_712, f'Paymaster Velocore approve {token_to_approve["name"]}')

    @exception_handler()
    def buy_token(self):
        balance = self.get_native_balance()
        if balance < Web3.to_wei(0.0005, 'ether'):
            logger.error('Balance < 0.0005 ETH\n')
            return False

        eth_mask = '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
        token_to_buy = random.choice(TOKEN)
        at_most = 1
        _all = 2
        to_index_id = 0x00
        reverse_flag = True

        prescale = random.uniform(VALUE_PRESCALE_SWAP[0], VALUE_PRESCALE_SWAP[1])
        value_from_vei = round(Web3.from_wei(balance * prescale, 'ether'), VALUE_PRESCALE_SWAP[2])
        amount_in_wei = Web3.to_wei(value_from_vei, 'ether')

        min_amount_out = self.get_min_amount_out(eth_mask, token_to_buy['address'], reverse_flag, token_to_buy['pool'], [0, amount_in_wei])

        txn = self.router_contract.functions.execute(
            [
                abi.encode(['address'], [token_to_buy['address']]),
                eth_mask,
            ],
            [
                0,
                0
            ],
            [
                [
                    abi.encode(['address'], [token_to_buy['pool']]),
                    [
                        self.to_token_info(0x00, at_most if reverse_flag else _all),
                        self.to_token_info(0x01, _all if reverse_flag else at_most),
                    ],
                    '0x00'
                ],
                [
                    "0x0500000000000000000000000000000000000000000000000000000000000000",
                    [
                        self.to_token_info(to_index_id, at_most, min_amount_out),
                    ],
                    '0x00'
                ]
            ]
        ).build_transaction({
            'from': self.address_wallet,
            'value': amount_in_wei,
            'nonce': self.web3.eth.get_transaction_count(self.address_wallet),
            **self.get_gas_price()
        })

        token_balance = self.get_token_balance(token_to_buy['address'])
        if token_balance < self.to_wei(token_to_buy['decimal'], 3):
            self.send_transaction_and_wait(txn, f'Buy {self.from_wei(token_to_buy["decimal"], min_amount_out)} {token_to_buy["name"]} on Velocore')
            return token_to_buy
        else:

            if token_to_buy['name'] == 'DAI':
                min_allowance = 696493865665783254
            else:
                min_allowance = 1436595
            paymaster_params = PaymasterParams(**{
                "paymaster": Web3.to_checksum_address(self.paymaster_address),
                "paymaster_input": self.web3.to_bytes(hexstr=PaymasterFlowEncoder(self.web3).encode_approval_based(token_to_buy["address"], min_allowance, b''))
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

            self.send_transaction_712_and_wait(tx_712, f'Paymaster buy {self.from_wei(token_to_buy["decimal"], min_amount_out)} {token_to_buy["name"]} Velocore')
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

        eth_mask = '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
        at_most = 1
        _all = 2
        to_index_id = 0x01
        reverse_flag = False

        min_amount_out = self.get_min_amount_out(token_to_sold['address'], eth_mask,  reverse_flag, token_to_sold['pool'], [balance_token, 0])

        txn = self.router_contract.functions.execute(
            [
                abi.encode(['address'], [token_to_sold['address']]),
                eth_mask,
            ],
            [
                balance_token,
                0
            ],
            [
                [
                    abi.encode(['address'], [token_to_sold['pool']]),
                    [
                        self.to_token_info(0x00, at_most if reverse_flag else _all),
                        self.to_token_info(0x01, _all if reverse_flag else at_most),
                    ],
                    '0x00'
                ],
                [
                    "0x0500000000000000000000000000000000000000000000000000000000000000",
                    [
                        self.to_token_info(to_index_id, at_most, min_amount_out),
                    ],
                    '0x00'
                ]
            ]
        ).build_transaction({
            'from': self.address_wallet,
            'nonce': self.web3.eth.get_transaction_count(self.address_wallet),
            **self.get_gas_price()
        })

        if token_to_sold['name'] == 'DAI':
            min_allowance = 696493865665783254
        else:
            min_allowance = 1436595

        paymaster_params = PaymasterParams(**{
            "paymaster": Web3.to_checksum_address(self.paymaster_address),
            "paymaster_input": self.web3.to_bytes(hexstr=PaymasterFlowEncoder(self.web3).encode_approval_based(token_to_sold['address'], min_allowance, b''))

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

        self.send_transaction_712_and_wait(tx_712, f'Paymaster sold {self.from_wei(token_to_sold["decimal"], balance_token)} {token_to_sold["name"]} Velocore')
