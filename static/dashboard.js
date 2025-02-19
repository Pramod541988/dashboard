$(document).ready(function () {
    let isCopyTradingEnabled = false;
    let selectedOrders = new Set();
    let selectedPositions = new Map(); // Changed from Set to Map to track multiple selections

    function fetchData(url, tableId, category, fields) {
        $.get(url, function (response) {
            let tableBody = $(tableId);
            tableBody.empty();

            if (response[category] && response[category].length > 0) {
                response[category].forEach(row => {
                    let rowId = `${category}_${row.order_id || row.symbol}_${row.name}`;
                    let isChecked = selectedPositions.has(rowId) || selectedOrders.has(rowId);

                    let tr = "<tr>";
                    tr += `<td><input type="checkbox" class="select-item" data-id="${rowId}" data-symbol="${row.symbol}" ${isChecked ? "checked" : ""}></td>`;

                    fields.forEach((field, index) => {
                        let cellValue = row[field] !== undefined && row[field] !== null ? row[field] : "N/A";

                        // Apply color to Net Profit column
                        if (field === "net_profit") {
                            let colorClass = parseFloat(cellValue) >= 0 ? "text-success" : "text-danger";
                            tr += `<td class="fw-bold ${colorClass}">${cellValue}</td>`;
                        } else {
                            tr += `<td>${cellValue}</td>`;
                        }
                    });

                    tr += "</tr>";
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

    $(document).on('change', '.select-item', function () {
        let rowId = $(this).data("id");
        let symbol = $(this).data("symbol");

        if ($(this).prop("checked")) {
            selectedPositions.set(rowId, true);
        } else {
            selectedPositions.delete(rowId);
        }
    });

    $('#cancelOrder').click(function () {
        let selectedOrderList = Array.from(selectedOrders).map(id => {
            let row = $(`input[data-id='${id}']`).closest('tr');
            return {
                name: row.find('td:eq(1)').text().trim(),
                symbol: row.find('td:eq(2)').text().trim(),
                order_id: row.find('td:eq(7)').text().trim()
            };
        });

        if (selectedOrderList.length === 0) {
            alert("No orders selected for cancellation.");
            return;
        }

        $.ajax({
            url: '/cancel_order',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ orders: selectedOrderList }),
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
        let selectedPositionList = Array.from(selectedPositions.keys()).map(id => {
            let row = $(`input[data-id='${id}']`).closest('tr');
            let quantity = Math.abs(parseInt(row.find('td:eq(3)').text()));

            return {
                name: row.find('td:eq(1)').text().trim(),
                symbol: row.find('td:eq(2)').text().trim(),
                quantity: quantity,
                transaction_type: parseInt(row.find('td:eq(3)').text()) > 0 ? "SELL" : "BUY"
            };
        });

        if (selectedPositionList.length === 0) {
            alert("No positions selected for closing.");
            return;
        }

        $.ajax({
            url: '/close_position',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ positions: selectedPositionList }),
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

    setInterval(refreshAll, 1000);  // Auto-refresh every second
    refreshAll();
});
