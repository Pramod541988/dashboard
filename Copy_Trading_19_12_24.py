import os
import time
import requests
import pandas as pd
from datetime import datetime
import logging

# Load Excel
try:
    excel_file = os.path.join(os.getcwd(), "data", "access_token.xlsx")
    df = pd.read_excel(excel_file)
except Exception as e:
    print("Error loading Excel file:", e)
    # Create data directory if it doesn't exist
    os.makedirs(os.path.join(os.getcwd(), "data"), exist_ok=True)
    # Create empty DataFrame with required columns
    df = pd.DataFrame(columns=['name', 'client_id', 'access_token', 'Type', 'Multiplier'])
    df.to_excel(excel_file, index=False)
    print(f"Created new Excel template at: {excel_file}")


# Clean up the 'Type' column
df['Type'] = df['Type'].str.strip().str.lower()

# Debug the cleaned DataFrame
print("Cleaned DataFrame:")
print(df)
print("Unique 'Type' values:", df['Type'].unique())

# Ensure there is a master account
master_account = df[df['Type'] == 'master']
if master_account.empty:
    print("No master account found in the Excel file. Please check the data.")
    exit()

# Select the first row for the master account
master_account = master_account.iloc[0]

# Extract child accounts
child_accounts = df[df['Type'] == 'child']
if child_accounts.empty:
    print("No child accounts found in the Excel file. Please check the data.")
    exit()

print("Master Account:", master_account)
print("Child Accounts:")
print(child_accounts)

# Create a day-wise folder for logs
today_date = datetime.now().strftime('%Y-%m-%d')
log_folder = os.path.join(os.getcwd(), today_date)
os.makedirs(log_folder, exist_ok=True)

# Initialize loggers for each child account
loggers = {}
for _, child in child_accounts.iterrows():
    child_name = child['name']
    log_file = os.path.join(log_folder, f"{child_name}.log")
    logger = logging.getLogger(child_name)
    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(log_file)
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    loggers[child_name] = logger

# Function to log messages to a specific child's log
def log_message(child_name, message):
    if child_name in loggers:
        loggers[child_name].debug(message)

# Initialize mappings and processed order IDs
order_mapping = {}  # Dictionary to store master-child order mappings
processed_order_ids_placed = set()  # Set to store processed order IDs for placement
processed_order_ids_canceled = set()  # Set to store processed order IDs for cancellation

# Function to fetch master orders
def fetch_master_orders(access_token):
    url = "https://api.dhan.co/v2/orders"
    headers = {"Content-Type": "application/json", "access-token": access_token}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        orders = response.json()
        return orders
    else:
        print("Failed to fetch master orders:", response.text)
        return []

# Function to place orders in child accounts
def place_order(access_token, client_id, order_details, child_name):
    url = "https://api.dhan.co/v2/orders"
    headers = {"Content-Type": "application/json", "access-token": access_token}
    order_details["dhanClientId"] = client_id
    log_message(child_name, f"Placing order with details: {order_details}")
    response = requests.post(url, headers=headers, json=order_details)
    if response.status_code == 200:
        order_id = response.json().get("orderId")
        log_message(child_name, f"Order placed successfully with ID {order_id}")
        return order_id
    else:
        log_message(child_name, f"Failed to place order: {response.text}")
        return None

# Function to cancel an order in child accounts
def cancel_order(access_token, order_id, child_name):
    url = f"https://api.dhan.co/v2/orders/{order_id}"
    headers = {"Content-Type": "application/json", "access-token": access_token}
    log_message(child_name, f"Cancelling Order {order_id}")
    response = requests.delete(url, headers=headers)
    if response.status_code == 200:
        log_message(child_name, f"Order {order_id} canceled successfully.")
    else:
        log_message(child_name, f"Failed to cancel order {order_id}: {response.text}")

# Function to convert `updateTime` to a timestamp
def convert_update_time(update_time_str):
    try:
        return int(datetime.strptime(update_time_str, "%Y-%m-%d %H:%M:%S").timestamp())
    except ValueError:
        print(f"Invalid updateTime format: {update_time_str}")
        return None

# Function to process a single order based on its status
def process_order(order):
    global order_mapping, processed_order_ids_placed, processed_order_ids_canceled

    order_id = order.get("orderId")
    update_time_str = order.get("updateTime")
    order_status = order.get("orderStatus")
    order_type = order.get("orderType")  # Get the order type

    # Convert `updateTime` to a timestamp
    update_time = convert_update_time(update_time_str) if update_time_str else None

    if not update_time:
        print(f"Order {order_id} has no valid updateTime. Skipping...")
        return

    # Check timing for placement or cancellation separately
    current_time = int(time.time())

    # Process market orders or pending orders
    if order_type == "MARKET" or order_status == "PENDING" or order_status == "TRADED":
        if order_id in processed_order_ids_placed or current_time - update_time > 5:
            return
        print(f"Placing Order {order_id} with status {order_status} and type {order_type}")

        # Place orders in child accounts
        for _, child in child_accounts.iterrows():
            multiplier = child['Multiplier']
            child_order_details = {
                "dhanClientId": child['client_id'],
                "correlationId": f"copy_{order_id}",
                "transactionType": order["transactionType"],
                "exchangeSegment": order["exchangeSegment"],
                "productType": order["productType"],
                "orderType": "MARKET" if order_type == "MARKET" else order["orderType"],
                "validity": order["validity"],
                "securityId": order["securityId"],
                "quantity": int(order["quantity"]) * multiplier,
                "price": order.get("price", ""),
                "triggerPrice": order.get("triggerPrice", "")
            }
            child_order_id = place_order(child['access_token'], child['client_id'], child_order_details, child['name'])
            if child_order_id:
                order_mapping.setdefault(order_id, {})[child['client_id']] = child_order_id
            else:
                log_message(child['name'], f"Order copy failed.")
        processed_order_ids_placed.add(order_id)

    elif order_status == "CANCELLED":
        if order_id in processed_order_ids_canceled or current_time - update_time > 5:
            return
        print(f"Cancelling Order {order_id} with status {order_status}")

        # Cancel orders in child accounts
        if order_id in order_mapping:
            for _, child in child_accounts.iterrows():
                child_id = child['client_id']
                child_order_id = order_mapping[order_id].get(child_id)
                if child_order_id:
                    cancel_order(child['access_token'], child_order_id, child['name'])
        processed_order_ids_canceled.add(order_id)

# Function to synchronize orders between master and child accounts
def synchronize_orders():
    master_orders = fetch_master_orders(master_account['access_token'])
    for order in master_orders:
        process_order(order)

# Main function
def main():
    while True:
        try:
            synchronize_orders()
            time.sleep(1)  # Minimum refresh time
        except Exception as e:
            print("Error in synchronization:", str(e))

# Run the script
if __name__ == "__main__":
    main()
