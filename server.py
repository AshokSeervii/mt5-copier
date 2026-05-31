import MetaTrader5 as mt5
import time
import requests
import json
from datetime import datetime

# ===== YOUR ACCOUNT DETAILS =====
MASTER_LOGIN = 123456        # change to your master account number
MASTER_PASSWORD = "yourpassword"   # change to your master password
MASTER_SERVER = "BrokerName-Live"  # change to your broker server name

FOLLOWER_ACCOUNTS = [
    {"login": 654321, "password": "followerpass1", "server": "BrokerName-Live"},
    {"login": 789012, "password": "followerpass2", "server": "BrokerName-Live"},
]

# ===== SETTINGS =====
COPY_RATIO = 1.0  # 1.0 means copy exact lot size, 0.5 means half lots
CHECK_INTERVAL = 1  # check every 1 second

known_trades = {}

def connect(login, password, server):
    mt5.initialize()
    connected = mt5.login(login, password=password, server=server)
    if connected:
        print(f"Connected to account {login}")
    else:
        print(f"Failed to connect to {login}: {mt5.last_error()}")
    return connected

def get_open_trades():
    positions = mt5.positions_get()
    if positions is None:
        return {}
    return {p.ticket: p for p in positions}

def open_trade(symbol, order_type, volume, price, sl, tp):
    order_type_mt5 = mt5.ORDER_TYPE_BUY if order_type == "buy" else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type_mt5,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": 999999,
        "comment": "copier",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    print(f"Trade opened: {result}")
    return result

def close_trade(ticket, symbol, order_type, volume):
    close_type = mt5.ORDER_TYPE_SELL if order_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = mt5.symbol_info_tick(symbol).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(symbol).ask
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": close_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": 999999,
        "comment": "copier close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    print(f"Trade closed: {result}")
    return result

def run_copier():
    print("Starting MT5 Trade Copier...")
    connect(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER)
    
    while True:
        try:
            current_trades = get_open_trades()
            
            # find new trades
            for ticket, position in current_trades.items():
                if ticket not in known_trades:
                    print(f"New trade detected: {position.symbol} {position.type} {position.volume}")
                    known_trades[ticket] = position
                    
                    # copy to all followers
                    for follower in FOLLOWER_ACCOUNTS:
                        mt5.initialize()
                        mt5.login(follower["login"], password=follower["password"], server=follower["server"])
                        order_type = "buy" if position.type == mt5.ORDER_TYPE_BUY else "sell"
                        volume = round(position.volume * COPY_RATIO, 2)
                        price = mt5.symbol_info_tick(position.symbol).ask if order_type == "buy" else mt5.symbol_info_tick(position.symbol).bid
                        open_trade(position.symbol, order_type, volume, price, position.sl, position.tp)
                        
                    # reconnect to master
                    connect(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER)

            # find closed trades
            for ticket in list(known_trades.keys()):
                if ticket not in current_trades:
                    closed = known_trades.pop(ticket)
                    print(f"Trade closed on master: {closed.symbol}")
                    
                    for follower in FOLLOWER_ACCOUNTS:
                        mt5.initialize()
                        mt5.login(follower["login"], password=follower["password"], server=follower["server"])
                        follower_positions = mt5.positions_get(symbol=closed.symbol)
                        if follower_positions:
                            for fp in follower_positions:
                                if fp.comment == "copier":
                                    close_trade(fp.ticket, fp.symbol, fp.type, fp.volume)
                    
                    connect(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER)

        except Exception as e:
            print(f"Error: {e}")
            connect(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_copier()
