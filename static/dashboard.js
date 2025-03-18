$(document).ready(function () {
    let selectedPositions = {};

    function fetchData(url, tableId, category, fields) {
        $.get(url, function (response) {
            let tableBody = $(tableId);
            tableBody.empty();

            if (response[category] && response[category].length > 0) {
                response[category].forEach(row => {
                    let tr = $("<tr>");
                    let rowId = `${row["name"]}-${row["symbol"]}-${row["order_id"]}`; // Unique row ID based on Name + Symbol + Order ID

                    // Checkbox for individual selection
                    let checkbox = $("<input>")
                        .attr("type", "checkbox")
                        .addClass("select-item")
                        .attr("data-row-id", rowId);

                    // Restore selection state
                    if (selectedPositions[rowId]) {
                        checkbox.prop("checked", true);
                    }

                    checkbox.change(function () {
                        if (this.checked) {
                            selectedPositions[rowId] = true;
                        } else {
                            delete selectedPositions[rowId];
                        }
                    });

                    tr.append($("<td>").append(checkbox));

                    fields.forEach(field => {
                        let cell = $("<td>").text(row[field] !== undefined && row[field] !== null ? row[field] : "N/A");

                        // Highlight Net Profit column with color
                        if (field === "net_profit") {
                            let profitValue = parseFloat(row[field]);
                            if (!isNaN(profitValue)) {
                                cell.css({
                                    "font-weight": "bold",
                                    "color": profitValue < 0 ? "red" : "green"
                                });
                            }
                        }

                        tr.append(cell);
                    });

                    tableBody.append(tr);
                });
            } else {
                tableBody.append(`<tr><td colspan="${fields.length + 1}">No data available</td></tr>`);
            }
        }).fail(function (xhr) {
            console.error(`Error fetching ${category} data: `, xhr.responseText);
        });
    }

    function refreshAll() {
        fetchData('/get_orders', '#pending_orders_table', 'pending', ['name', 'symbol', 'transaction_type', 'quantity', 'price', 'status', 'order_id']);
        fetchData('/get_orders', '#cancelled_orders_table', 'cancelled', ['name', 'symbol', 'transaction_type', 'quantity', 'price', 'status', 'order_id']);
        fetchData('/get_orders', '#traded_orders_table', 'traded', ['name', 'symbol', 'transaction_type', 'quantity', 'price', 'status', 'order_id']);
        fetchData('/get_orders', '#rejected_orders_table', 'rejected', ['name', 'symbol', 'transaction_type', 'quantity', 'price', 'status', 'order_id']);
        fetchData('/get_orders', '#others_orders_table', 'others', ['name', 'symbol', 'transaction_type', 'quantity', 'price', 'status', 'order_id']);
        fetchData('/get_positions', '#open_positions_table', 'open', ['name', 'symbol', 'quantity', 'buy_avg', 'sell_avg', 'net_profit']);
        fetchData('/get_positions', '#closed_positions_table', 'closed', ['name', 'symbol', 'quantity', 'buy_avg', 'sell_avg', 'net_profit']);
    }

    $('#refreshOrders').click(refreshAll);
    $('#refreshPositions').click(refreshAll);

    $('#cancelOrder').click(function () {
        let selectedOrders = [];
        $('#pending_orders_table .select-item:checked').each(function () {
            let row = $(this).closest('tr');
            let orderData = {
                name: row.find('td:eq(1)').text(),
                symbol: row.find('td:eq(2)').text(),
                order_id: row.find('td:eq(7)').text().trim()
            };
            selectedOrders.push(orderData);
        });

        if (selectedOrders.length === 0) {
            alert("No orders selected for cancellation.");
            return;
        }

        $.ajax({
            url: '/cancel_order',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ orders: selectedOrders }),
            success: function (response) {
                alert(response.message.join("\n"));
                refreshAll();
            },
            error: function (xhr) {
                alert("Failed to cancel orders. Error: " + xhr.responseText);
                console.error("Cancel Order Error:", xhr.responseText);
            }
        });
    });

    $('#closePosition').click(function () {
        let selectedPositionsArray = [];
        $('#open_positions_table .select-item:checked').each(function () {
            let row = $(this).closest('tr');
            let quantity = Math.abs(parseInt(row.find('td:eq(3)').text()));

            let positionData = {
                name: row.find('td:eq(1)').text().trim(),
                symbol: row.find('td:eq(2)').text().trim(),
                quantity: quantity,
                transaction_type: parseInt(row.find('td:eq(3)').text()) > 0 ? "SELL" : "BUY"
            };

            selectedPositionsArray.push(positionData);
        });

        if (selectedPositionsArray.length === 0) {
            alert("No positions selected for closing.");
            return;
        }

        $.ajax({
            url: '/close_position',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ positions: selectedPositionsArray }),
            success: function (response) {
                alert(response.message.join("\n"));
                refreshAll();
            },
            error: function (xhr) {
                alert("Failed to close positions. Error: " + xhr.responseText);
                console.error("Close Position Error:", xhr.responseText);
            }
        });
    });

    // Copy Trading Enable/Disable Logic
    $('#toggleCopyTrading').change(function () {
        isCopyTradingEnabled = $(this).is(':checked');
        $('#refreshCopyTrading').prop('disabled', !isCopyTradingEnabled);

        $.ajax({
            url: '/toggle_copy_trading',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ enabled: isCopyTradingEnabled }),
            success: function (response) {
                alert(response.message);
            },
            error: function (xhr) {
                alert("Failed to toggle Copy Trading: " + xhr.responseText);
                console.error("Error:", xhr.responseText);
            }
        });
    });

    $('#refreshCopyTrading').click(function () {
        if (!isCopyTradingEnabled) {
            alert("Copy Trading is disabled.");
            return;
        }

        $.get('/get_copy_trading_logs', function (logs) {
            let tableBody = $('#copy_trading_table');
            tableBody.empty();

            if (logs && logs.length > 0) {
                logs.forEach(log => {
                    let row = `<tr><td>${log.time}</td><td>${log.account}</td><td>${log.message}</td></tr>`;
                    tableBody.append(row);
                });
            } else {
                tableBody.append('<tr><td colspan="3">No logs available</td></tr>');
            }
        }).fail(function (xhr) {
            console.error("Failed to fetch copy trading logs:", xhr.responseText);
        });
    });

    // Auto-refresh existing data every second
    setInterval(refreshAll, 1000);
    refreshAll();
});
