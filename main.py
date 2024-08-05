from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import db_helper
import generic_helper

app = FastAPI()

inprogress_orders = {}

@app.post("/")
async def handle_request(request: Request):
    payload = await request.json()
    intent = payload['queryResult']['intent']['displayName']
    parameters = payload['queryResult']['parameters']
    output_contexts = payload['queryResult'].get('outputContexts', [])
    session_id = generic_helper.extract_session_id(output_contexts[0]["name"]) if output_contexts else None

    intent_handler_dict = {
        'order.add - context: ongoing-order': add_to_order,
        'order.remove - context: ongoing-order': remove_from_order,
        'order.complete - context: ongoing-order': complete_order,
        'track.order - context: ongoing-tracking': track_order
    }

    return await intent_handler_dict.get(intent, default_response)(parameters, session_id)

def default_response(parameters, session_id):
    return JSONResponse(content={"fulfillmentText": "Invalid intent received"})

async def complete_order(parameters, session_id):
    if session_id not in inprogress_orders:
        fulfillment_text = "I'm having trouble finding your order. Please place a new order."
    else:
        order = inprogress_orders[session_id]
        order_id = await save_to_db(order)
        if order_id == -1:
            fulfillment_text = "Sorry, there was an error processing your order. Please try again."
        else:
            order_total = db_helper.get_total_order_price(order_id)
            order_status = db_helper.get_order_status(order_id)
            fulfillment_text = f"Your order has been placed. Order ID: {order_id}. Total amount: {order_total}. Order Status: {order_status}"

        del inprogress_orders[session_id]

    return JSONResponse(content={"fulfillmentText": fulfillment_text})

async def save_to_db(order: dict):
    try:
        next_order_id = db_helper.get_next_order_id()

        for food_item, quantity in order.items():
            rcode = db_helper.insert_order_item(
                food_item,
                quantity,
                next_order_id
            )

            if rcode == -1:
                return -1

        db_helper.insert_order_tracking(next_order_id, "in progress")

        return next_order_id
    except Exception as e:
        print(f"Error saving order to database: {str(e)}")
        return -1

async def add_to_order(parameters, session_id):
    food_items = parameters.get("food-item", [])
    quantities = parameters.get("number", [])

    if len(food_items) != len(quantities):
        fulfillment_text = "Please specify both food items and quantities clearly."
    else:
        new_food_dict = dict(zip(food_items, quantities))

        if session_id in inprogress_orders:
            current_food_dict = inprogress_orders[session_id]
            current_food_dict.update(new_food_dict)
            inprogress_orders[session_id] = current_food_dict
        else:
            inprogress_orders[session_id] = new_food_dict

        order_str = generic_helper.get_str_from_food_dict(inprogress_orders[session_id])
        fulfillment_text = f"Added items: {order_str}. Anything else?"

    return JSONResponse(content={"fulfillmentText": fulfillment_text})

async def remove_from_order(parameters, session_id):
    if session_id not in inprogress_orders:
        return JSONResponse(content={"fulfillmentText": "I'm having trouble finding your order. Please place a new order."})
    
    food_items = parameters.get("food-item", [])
    current_order = inprogress_orders[session_id]

    removed_items = []
    no_such_items = []

    for item in food_items:
        if item not in current_order:
            no_such_items.append(item)
        else:
            removed_items.append(item)
            del current_order[item]

    if len(removed_items) > 0:
        fulfillment_text = f'Removed items: {", ".join(removed_items)} from your order.'

    if len(no_such_items) > 0:
        fulfillment_text = f'Your current order does not have: {", ".join(no_such_items)}'

    if len(current_order.keys()) == 0:
        fulfillment_text += " Your order is empty!"
    else:
        order_str = generic_helper.get_str_from_food_dict(current_order)
        fulfillment_text += f" Remaining items: {order_str}"

    return JSONResponse(content={"fulfillmentText": fulfillment_text})

async def track_order(parameters, session_id):
    order_id = parameters.get('order-id')

    if order_id:
        try:
            order_id = int(order_id)
            order_status = db_helper.get_order_status(order_id)
            if order_status:
                fulfillment_text = f"Order status for Order ID {order_id}: {order_status}"
            else:
                fulfillment_text = f"No order found with Order ID: {order_id}"
        except ValueError:
            fulfillment_text = "Invalid Order ID provided."
    else:
        fulfillment_text = "Order ID not provided."

    return JSONResponse(content={"fulfillmentText": fulfillment_text})
