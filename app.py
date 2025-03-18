import pandas as pd
import json
import time
import threading
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from flask_cors import CORS  # ✅ Import CORS
from dhanhq import dhanhq
import os
import logging
from datetime import datetime
from Copy_Trading_19_12_24 import synchronize_orders

# Logging (stdout for Render)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# Load client credentials
def load_clients():
    df = pd.read_excel("clients.xlsx")
    df.columns = df.columns.str.strip().str.lower()
    if {"name", "client_id", "access_token"} - set(df.columns):
        raise ValueError("Excel file must contain 'name', 'client_id', and 'access_token' columns.")
    return {row["name"]: {"client_id": row["client_id"], "access_token": row["access_token"]} for _, row in df.iterrows()}

clients = load_clients()

app = Flask(__name__)
CORS(app)  # ✅ Enable CORS for all routes
socketio = SocketIO(app, cors_allowed_origins="*")

categorized_orders = {"pending": [], "traded": [], "rejected": [], "cancelled": [], "others": []}
categorized_positions = {"open": [], "closed": []}

copy_trading_enabled = False
copy_trading_running = False

def run_copy_trading():
    global copy_trading_running
    copy_trading_running = True
    logging.info("Copy Trading function started.")
    try:
        while copy_trading_enabled:
            synchronize_orders()
            time.sleep(1)
    except Exception as e:
        logging.error("Error in Copy Trading: %s", str(e))
    finally:
        logging.info("Copy Trading function stopped.")
        copy_trading_running = False

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/get_orders")
def get_orders():
    return jsonify(categorized_orders)

@app.route("/get_positions")
def get_positions():
    return jsonify(categorized_positions)

@app.route("/toggle_copy_trading", methods=["POST"])
def toggle_copy_trading():
    global copy_trading_enabled
    data = request.json
    copy_trading_enabled = data.get("enabled", False)
    message = "Copy Trading Enabled" if copy_trading_enabled else "Copy Trading Disabled"
    logging.info(message)

    if copy_trading_enabled:
        threading.Thread(target=run_copy_trading, daemon=True).start()

    return jsonify({"message": message})

@app.route("/get_copy_trading_status")
def get_copy_trading_status():
    status = "Running" if copy_trading_running else "Stopped"
    return jsonify({"status": status})

def fetch_orders():
    global categorized_orders
    while True:
        updated_orders = {key: [] for key in categorized_orders}
        for client_name, creds in clients.items():
            try:
                dhan = dhanhq(creds["client_id"], creds["access_token"])
                response = dhan.get_order_list()
                if isinstance(response, str):
                    response = json.loads(response)

                if "data" in response and isinstance(response["data"], list):
                    for order in response["data"]:
                        order_data = {
                            "name": client_name,
                            "symbol": order.get("tradingSymbol", "N/A"),
                            "transaction_type": order.get("transactionType", "N/A"),
                            "quantity": order.get("quantity", 0),
                            "price": order.get("price", 0.0),
                            "status": order.get("orderStatus", "UNKNOWN"),
                            "order_id": order.get("orderId", "N/A")
                        }
                        status = order_data["status"].lower()
                        if status in updated_orders:
                            updated_orders[status].append(order_data)
                        else:
                            updated_orders["others"].append(order_data)
            except Exception as e:
                logging.error("Error fetching orders for %s: %s", client_name, str(e))
        categorized_orders = updated_orders
        socketio.emit("update_orders", categorized_orders)
        time.sleep(1)

def fetch_positions():
    global categorized_positions
    while True:
        updated_positions = {"open": [], "closed": []}
        for client_name, creds in clients.items():
            try:
                dhan = dhanhq(creds["client_id"], creds["access_token"])
                response = dhan.get_positions()
                if isinstance(response, str):
                    response = json.loads(response)

                if "data" in response and isinstance(response["data"], list):
                    for position in response["data"]:
                        net_qty = position.get("netQty", 0)
                        security_id = position.get("securityId", "N/A")  # Fetch Security ID
                        position_data = {
                            "name": client_name,
                            "symbol": position.get("tradingSymbol", "N/A"),
                            "security_id": security_id,
                            "quantity": net_qty,
                            "buy_avg": position.get("buyAvg", "N/A"),
                            "sell_avg": position.get("sellAvg", "N/A"),
                            "net_profit": position.get("realizedProfit", 0.0) + position.get("unrealizedProfit", 0.0),
                            "transaction_type": "BUY" if net_qty > 0 else "SELL" if net_qty < 0 else "CLOSED"
                        }
                        if net_qty == 0:
                            updated_positions["closed"].append(position_data)
                        else:
                            updated_positions["open"].append(position_data)
            except Exception as e:
                logging.error("Error fetching positions for %s: %s", client_name, str(e))
        categorized_positions = updated_positions
        socketio.emit("update_positions", categorized_positions)
        time.sleep(1)

if __name__ == "__main__":
    logging.info("Starting Flask app...")

    threading.Thread(target=fetch_orders, daemon=True).start()
    threading.Thread(target=fetch_positions, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
