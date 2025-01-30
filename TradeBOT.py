import time
import os
import schedule
import pandas as pd
from datetime import datetime, timedelta
from fyers_apiv3 import fyersModel

# Function to read the content of a file
def read_file(file_path):
    with open(file_path, 'r') as file:
        return file.read().strip()

# Read fyers_appid and fyers_token from the root folder
fyers_appid = read_file('fyers_appid.txt')
fyers_token = read_file('fyers_token.txt')

# Create log path directory if it doesn't exist
log_path = 'log_path'
os.makedirs(log_path, exist_ok=True)

# Initialize the Fyers API client
is_async = False
fyers = fyersModel.FyersModel(client_id=fyers_appid, token=fyers_token, is_async=is_async, log_path=log_path)

# Mapping of month to expiry letter for monthly expiries
expiry_monthly_map = {
    'Jan': 'JAN',
    'Feb': 'FEB',
    'Mar': 'MAR',
    'Apr': 'APR',
    'May': 'MAY',
    'Jun': 'JUN',
    'Jul': 'JUL',
    'Aug': 'AUG',
    'Sep': 'SEP',
    'Oct': 'OCT',
    'Nov': 'NOV',
    'Dec': 'DEC'
}

# Configurable quantities
BUY_QUANTITY = 75
SELL_QUANTITY = 75
MAX_LOSS = -1500

# Function to fetch the first 15-minute candle data
def fetch_first_15_min_candle(symbol, interval='15'):
    today_date = datetime.now().strftime("%Y-%m-%d")
    data = {
        "symbol": symbol,
        "resolution": interval,
        "date_format": "1",
        "range_from": today_date,
        "range_to": today_date,
        "cont_flag": "1"
    }
    response = fyers.history(data)
    if response['s'] == 'ok':
        df = pd.DataFrame(response['candles'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df.iloc[0]['high'], df.iloc[0]['low']
    else:
        print("Failed to fetch data:", response)
        return None, None

# Function to construct ITM option symbol
def get_in_the_money_option(spot_price, ce=True):
    strike_price = round(spot_price / 50) * 50
    option_type = "CE" if ce else "PE"

    today = datetime.now()
    last_day_of_month = today.replace(day=28) + timedelta(days=4)
    last_thursday_of_month = last_day_of_month - timedelta(days=(last_day_of_month.weekday() + 3) % 7)

    expiry_day = last_thursday_of_month.strftime('%d')
    expiry_month_code = expiry_monthly_map[last_thursday_of_month.strftime('%b')]
    expiry_year = last_thursday_of_month.strftime('%y')

    option_symbol = f"NSE:NIFTY{expiry_year}{expiry_month_code}{strike_price}{option_type}"
    return option_symbol

# Function to place an order
def place_order(symbol, qty, side, type="MARKET"):
    order_data = {
        "symbol": symbol,
        "qty": qty,
        "type": 2,
        "side": side,
        "productType": "INTRADAY",
        "limitPrice": 0,
        "stopPrice": 0,
        "validity": "DAY",
        "disclosedQty": 0,
        "offlineOrder": False
    }
    response = fyers.place_order(data=order_data)
    return response

# Function to buy a specified option
def buy_specified_option(symbol, qty):
    return place_order(symbol, qty, side=1)

# Function to monitor P&L
def monitor_pnl():
    data = fyers.positions()
    if data['s'] == 'ok':
        net_pnl = sum(position['netPnl'] for position in data['netPositions'])
        print(f"Current P&L: {net_pnl}")
        if net_pnl <= MAX_LOSS:
            print("Max loss limit reached. Exiting all positions.")
            exit_all_positions()
    else:
        print("Failed to fetch positions:", data)

# Function to exit all positions
def exit_all_positions():
    positions = fyers.positions()
    if positions['s'] == 'ok':
        for position in positions['netPositions']:
            if position['quantity'] != 0:
                side = -1 if position['quantity'] > 0 else 1
                place_order(position['symbol'], abs(position['quantity']), side)
        print("All positions exited.")
    else:
        print("Failed to fetch positions for exiting:", positions)

# Main trading function
def trade():
    symbol = 'NSE:NIFTY50-INDEX'
    high, low = fetch_first_15_min_candle(symbol)

    if high is None or low is None:
        print("Error fetching the first 15-minute candle data.")
        return

    print(f"First 15-minute candle high: {high}")
    print(f"First 15-minute candle low: {low}")

    specified_put_option = "NSE:NIFTY25JAN22550PE"
    specified_call_option = "NSE:NIFTY25JAN23600CE"

    market_data = fyers.quotes({"symbols": symbol})
    nifty_price = market_data['d'][0]['v']['lp']

    if nifty_price > high:
        buy_response = buy_specified_option(specified_put_option, qty=BUY_QUANTITY)
        print(f"Bought specified PE option: {specified_put_option}, Response: {buy_response}")

        itm_put_option = get_in_the_money_option(nifty_price, ce=False)
        sell_response = place_order(itm_put_option, qty=SELL_QUANTITY, side=-1)
        print(f"Sold ITM PE option: {itm_put_option}, Response: {sell_response}")

    elif nifty_price < low:
        buy_response = buy_specified_option(specified_call_option, qty=BUY_QUANTITY)
        print(f"Bought specified CE option: {specified_call_option}, Response: {buy_response}")

        itm_call_option = get_in_the_money_option(nifty_price, ce=True)
        sell_response = place_order(itm_call_option, qty=SELL_QUANTITY, side=-1)
        print(f"Sold ITM CE option: {itm_call_option}, Response: {sell_response}")

    # Start monitoring P&L
    while True:
        monitor_pnl()
        time.sleep(10)

# Schedule and monitor positions
def schedule_tasks():
    schedule.every().day.at("09:30").do(trade)
    schedule.every().day.at("15:13").do(exit_all_positions)  # Exit all positions at 3:13 PM

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    schedule_tasks()
