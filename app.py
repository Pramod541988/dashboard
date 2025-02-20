import pandas as pd
import json
import time
import threading
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from dhanhq import dhanhq
import os
import logging
from datetime import datetime
from Copy_Trading_19_12_24 import synchronize_orders  # Import Copy Trading logic

# Set up logging
log_folder = os.path.join(os.getcwd(), "logs")
os.makedirs(log_folder, exist_ok=True)
log_file = os.path.join(log_folder, "app.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

# Load client credentials
def load_clients():
    df = pd.read_csv("data/access_token.csv")
    df.columns = df.columns.str.strip().str.lower()
    if {"name", "client_id", "access_token"} - set(df.columns):
        raise ValueError("CSV file must contain 'name', 'client_id', and 'access_token' columns.")
    return {row["name"]: {"client_id": row["client_id"], "access_token": row["access_token"]} for _, row in df.iterrows()}


clients = load_clients()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

categorized_orders = {"pending": [], "traded": [], "rejected": [], "cancelled": [], "others": []}
categorized_positions = {"open": [], "closed": []}

copy_trading_enabled = False  # Global variable to track Copy Trading state
copy_trading_running = False  # Global variable to track if Copy Trading is running

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

@app.route("/cancel_order", methods=["POST"])
def cancel_order():
    data = request.json
    logging.info("Received cancel order request: %s", data)

    if "orders" not in data or not isinstance(data["orders"], list):
        return jsonify({"error": "Invalid request format"}), 400

    response_messages = []
    for order in data["orders"]:
        client = clients.get(order["name"])
        if client:
            try:
                dhan = dhanhq(client["client_id"], client["access_token"])
                cancel_response = dhan.cancel_order(order["order_id"])
                logging.info("Cancel response for %s: %s", order['order_id'], cancel_response)

                if cancel_response.get("status") == "success":
                    response_messages.append(f"Order {order['order_id']} canceled successfully.")
                else:
                    response_messages.append(f"Failed to cancel order {order['order_id']}: {cancel_response}")
            except Exception as e:
                logging.error("Error canceling order %s: %s", order['order_id'], str(e))
                response_messages.append(f"Error canceling order {order['order_id']}: {str(e)}")

    return jsonify({"message": response_messages})

@app.route("/close_position", methods=["POST"])
def close_position():
    data = request.json
    print("Received close position request:", data)  # Debugging print

    if "positions" not in data or not isinstance(data["positions"], list):
        return jsonify({"error": "Invalid request format"}), 400

    response_messages = []
    for position in data["positions"]:
        client = clients.get(position["name"])
        if client:
            try:
                dhan = dhanhq(client["client_id"], client["access_token"])
                matching_position = next(
                    (p for p in categorized_positions["open"] if p["symbol"] == position["symbol"]), None
                )

                if not matching_position:
                    response_messages.append(f"Error: Position {position['symbol']} not found")
                    continue

                security_id = matching_position["security_id"]
                quantity = abs(matching_position["quantity"])
                transaction_type = dhan.SELL if matching_position["transaction_type"] == "BUY" else dhan.BUY

                response = dhan.place_order(
                    security_id=security_id,
                    exchange_segment=dhan.NSE,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    order_type=dhan.MARKET,
                    product_type=dhan.INTRA,
                    price=0
                )
                print(f"Position {position['symbol']} closed: {response}")

                if response.get("status") == "success":
                    response_messages.append(f"Position {position['symbol']} closed successfully.")
                else:
                    response_messages.append(f"Failed to close position {position['symbol']}: {response}")

            except Exception as e:
                print(f"Error closing position {position['symbol']}: {e}")
                response_messages.append(f"Error closing position {position['symbol']}: {str(e)}")

    return jsonify({"message": response_messages}), 200

def fetch_orders():
    global categorized_orders
    while True:
        try:
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
                    else:
                        logging.error("Invalid response format for %s: %s", client_name, response)
                except Exception as e:
                    logging.error("Error fetching orders for %s: %s", client_name, str(e))
                    logging.debug("Full traceback:", exc_info=True)
            
            categorized_orders = updated_orders
            socketio.emit("update_orders", categorized_orders)
        except Exception as e:
            logging.error("Unexpected error in fetch_orders: %s", str(e))
            logging.debug("Full traceback:", exc_info=True)
        finally:
            time.sleep(1)


def fetch_positions():
    global categorized_positions
    while True:
        try:
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
                                "security_id": security_id,  # Store security ID for closing
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
                    else:
                        logging.error("Invalid response format for %s: %s", client_name, response)
                except Exception as e:
                    logging.error("Error fetching positions for %s: %s", client_name, str(e))
                    logging.debug("Full traceback:", exc_info=True)
            
            categorized_positions = updated_positions
            socketio.emit("update_positions", categorized_positions)
        except Exception as e:
            logging.error("Unexpected error in fetch_positions: %s", str(e))
            logging.debug("Full traceback:", exc_info=True)
        finally:
            time.sleep(1)


if __name__ == "__main__":
    logging.info("Flask app is running...")

    threading.Thread(target=fetch_orders, daemon=True).start()
    threading.Thread(target=fetch_positions, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    socketio.run(app, debug=False, host=host, port=port)
