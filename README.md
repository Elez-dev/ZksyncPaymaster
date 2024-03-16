[![Telegram channel](https://img.shields.io/endpoint?url=https://runkit.io/damiankrawczyk/telegram-badge/branches/master?url=https://t.me/developercode1)](https://t.me/developercode1)
[![PyPI supported Python versions](https://img.shields.io/badge/Python%203.10.10-8A2BE2)](https://www.python.org/downloads/release/python-31010/)

<div align="center">
  <img src="https://miro.medium.com/v2/resize:fit:1400/format:webp/1*WehIRwTjZydXnttPasC0iQ.jpeg"  />
  <h1>ZKSYNC ERA PAYMASTER</h1>
  <p>Software on ZKSYNC ERA - includes the ability to do commission-free swaps(PAYMASTER). Available platforms: Syncswap, Mute.io, Velocore</p>
</div>

---

🤠👉 <b>Our tg-channel:</b> [PYTHON DAO](https://t.me/developercode1)

🤗 <b>Supports:</b> elez-dev.eth

---
<h2>🙊 INFO</h2>

EN:

You need [Python 3.10.10](https://www.python.org/downloads/release/python-31010/) to work

This guide details how to install Python - [link](https://mirror.xyz/wiedzmin.eth/ygk2pzqaTKaHmnQuV1vV-morIstKnDTJnXPpBaZwnkQ)

1. In the _data_ folder fill the Excel file with private keys

2. All the settings happen in the _settings.py_ file - each line is signed

3. Run through the _main.py_ file

---
RU:

Для работы нужен [Python 3.10.10](https://www.python.org/downloads/release/python-31010/)

В данном гайде подробно описано как установить Python - [link](https://mirror.xyz/wiedzmin.eth/Z06W81VrxO9KI88vkcxeW0Lc8f2nBo5Wdyqce0HTNm8)

1. В папке _data_ заполняем Excel файл с приватными ключами

2. Все настройки происходят в файле _settings.py_ - каждая строчка подписана

3. Запускаем через файл _main.py_

---  
<h2>🙊 HOW IT WORKS</h2>

EN:

- Selects one of the three DEX
- Buys (USDC,USDT) on DEX with a regular transaction
- Does a paymaster approve for the USDC or USDT
- Does a swap for the stablecoins
- Goes to the next account or repeats the circle

---
RU:

- Выбирает одну из трёх свапалок
- Покупает на ней стейблы(USDC,USDT) обычной транзакцией
- Делает пеймастер апрув за стейблы
- Делает свап за стейблы
- Идет к следующем аккаунту или повторяет круг

---
<h2>🚀 INSTALLING AND RUNNING SOFTWARE</h2>

```

git clone https://github.com/Elez-dev/ZksyncPaymaster.git

cd ZksyncPaymaster-master

pip3.10 install -r requirements.txt

python3.10 main.py

```

---
<h2>❤️ Any questions in our chat - https://t.me/pythondao</h2>

