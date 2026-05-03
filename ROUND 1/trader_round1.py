from datamodel import (
    Listing,
    Observation,
    OrderDepth,
    UserId,
    TradingState,
    Order,
    ProsperityEncoder,
    Symbol,
    Trade,
)
from typing import List, Dict, Any
import jsonpickle
import json

class Trader:

    CONFIG = {
        "INTARIAN_PEPPER_ROOT": {
            "LIMIT" : 80,
            "MAKER_MARGIN": 7,
            "AVERAGE_SPREAD": 20,
            'TRADE_VOLUME' : 5,
            'TIME_TO_BUY_FULL' : 8000
        },
        "ASH_COATED_OSMIUM": {
            "LIMIT" : 80,
            "AVERAGE_SPREAD": 20,
            "TAKER_MARGIN": 1,
            "MAKER_MARGIN": 8,
            "SKEW_COEFF": 0,
            "IGNORE_TRADES_VALUE" : 2,
        },
    }

    def wall_mid_price(
        self, order_depth: OrderDepth, trader_data: str, params: Dict[str, Any]
    ) -> float:
        """Function implementing the wall_mid algorithm modified for prosperity4"""
        # MID_PRICE
        # Explanation: I implement Frankfurt's Wall Mid which is average of the two high-volume orders.
        # However this year, commonly there are days without one of the big offers, so I just make it up by 
        # adding/removing the average_spread when only one is present.
        #  When neither is present, i just use the previous price which is stored in traderData
        try:
            previous_price = float(trader_data)
        except:
            previous_price = 12001
        # calculating actual_price
        ask_wall = -1
        for ask_price, vol in order_depth.sell_orders.items():
            if vol < -15:
                ask_wall = ask_price
        bid_wall = -1
        for bid_price, vol in order_depth.buy_orders.items():
            if vol > 15:
                bid_wall = bid_price
        if bid_wall != -1 and ask_wall == -1:
            ask_wall = bid_wall + params["AVERAGE_SPREAD"]
        elif bid_wall == -1 and ask_wall != -1:
            bid_wall = ask_wall - params["AVERAGE_SPREAD"]
        if ask_wall == -1:
            actual_price = previous_price
        else:
            actual_price = (bid_wall + ask_wall) / 2
        mid_price = actual_price
        return mid_price

    def get_middest_bid_ask(
        self, state: TradingState, product: str, current_orders: List[Order]
    ):
        '''Receives a list of orders the strategy has done so far. It returns the highest bid and lowest ask, still on the market'''
        order_depth: OrderDepth = state.order_depths.get(product)
        highest_bid, highest_bid_volume = None, None
        lowest_ask, lowest_ask_volume = None, None

        if order_depth:
            if len(order_depth.buy_orders) > 0:
                highest_bid = min(order_depth.buy_orders.keys())
                highest_bid_volume = order_depth.buy_orders[highest_bid]
            if len(order_depth.sell_orders) > 0:
                lowest_ask = max(order_depth.sell_orders.keys())
                lowest_ask_volume = order_depth.sell_orders[lowest_ask]
            buy_orders = dict(order_depth.buy_orders)
            sell_orders = dict(order_depth.sell_orders)

            for order in current_orders:
                if order.symbol == product:
                    if order.quantity > 0 and order.price in buy_orders:
                        buy_orders[order.price] -= order.quantity
                        if buy_orders[order.price] <= 0:
                            del buy_orders[order.price]
                    elif order.quantity < 0 and order.price in sell_orders:
                        sell_orders[order.price] -= order.quantity
                        if sell_orders[order.price] >= 0:
                            del sell_orders[order.price]

            if len(buy_orders) > 0:
                highest_bid = max(buy_orders.keys())
                highest_bid_volume = buy_orders[highest_bid]
            if len(sell_orders) > 0:
                lowest_ask = min(sell_orders.keys())
                lowest_ask_volume = sell_orders[lowest_ask]

        return highest_bid, highest_bid_volume, lowest_ask, lowest_ask_volume

    def trade_pepper(
        self, state: TradingState, trader_data: str
    ) -> tuple[List[Order], str]:
        """Receives the TradingState plus trader_data extracted exactly for it. Must return a List[Order] and the new trader_data for itself"""
        product = "INTARIAN_PEPPER_ROOT"
        order_depth: OrderDepth = state.order_depths[product]
        orders: List[Order] = []
        params = self.CONFIG[product]
        limit = params['LIMIT']
        new_trader_data: str = trader_data
        current_pos = state.position.get(product, 0)

        # STRATEGY EXPLANATION
        # I buy immediteately at the beggining. However I do not rush buying all offers at timestamp 1, as some of them are quite
        # high. I found that its better to buy only the best one each timestamp. As the growth in the beginning is slower than
        # the spread. Another thing is I implemented wall_mid for mid price. I do not buy when the best offer is more than
        # mid price + maker_margin as again, growth is slower than spread. But all of those things give roughly like <1k pnl
        # After filling the position fully, we also implement a 

        mid_price = self.wall_mid_price(order_depth, trader_data, params)
        new_trader_data = str(mid_price)

        pos_for_buys = current_pos
        highest_bid, highest_bid_volume, lowest_ask, lowest_ask_volume = self.get_middest_bid_ask(state,product,[])

        if state.timestamp <= params['TIME_TO_BUY_FULL']:
            for ask_price, vol in sorted(order_depth.sell_orders.items()):
                if ask_price > (mid_price + params["MAKER_MARGIN"]):
                    break
                buy_vol = min(-vol, limit - pos_for_buys)
                orders.append(Order(product, int(ask_price), buy_vol))
                pos_for_buys += buy_vol
        else:
            if pos_for_buys == limit:
                if lowest_ask == None or lowest_ask<mid_price:
                    orders.append(Order(product,int(mid_price+params['MAKER_MARGIN']),-params['TRADE_VOLUME']))
                else:
                    orders.append(Order(product,lowest_ask-1,-params['TRADE_VOLUME']))
            else:
                if highest_bid == None or highest_bid>mid_price:
                    orders.append(Order(product,int(mid_price-params['MAKER_MARGIN']),limit-pos_for_buys))
                else:
                    orders.append(Order(product,highest_bid+1,limit-pos_for_buys))
        return orders, new_trader_data

    def trade_osmium(
        self, state: TradingState, trader_data: str
    ) -> tuple[List[Order], str]:
        """Receives the TradingState plus trader_data extracted exactly for it. Must return a List[Order] and the new trader_data for itself"""
        product = "ASH_COATED_OSMIUM"
        order_depth: OrderDepth = state.order_depths[product]
        orders: List[Order] = []
        params = self.CONFIG[product]
        new_trader_data: str = trader_data

        global_limit = params['LIMIT']
        current_pos = state.position.get(product, 0)

        # STRATEGY EXPLANATION
        # Calculates mid_price.
        #I use the wall_mid to calculate mid_price (look for documentatin in the function)
        #After having mid_price, I buy everything that is at mid_price-taker_margin or lower and
        #sell to everything that is at mid_price+taker_margin or higher, however the price is skewed a bit by a 
        # skewing coefficient, which makes it harder to buy when we have a big position and hard to sell when we have a 
        # small position. The goal is to not hold much at a time, because of unpredictable price fluctuations
        # But sssentially pick up the deals in the order book
        # After that I put waiting (maker) orders for bid at +1 of the best now, and for ask at -1 of the best 
        # If there arent none of those, I put simply at mid_price+-maker_margin
        # Another small improvement is to check if the current best bid or best ask have a really small volume, we can put
        # offers matching them, as the takers will use up the current best and then buy from us. But this gives a marginal
        # imrovement

        mid_price = self.wall_mid_price(order_depth, trader_data, params)
        new_trader_data = str(mid_price)
        skew = current_pos * params["SKEW_COEFF"]
        b_margin_t = params["TAKER_MARGIN"] + skew
        s_margin_t = params["TAKER_MARGIN"] - skew
        our_bid_t = int(round(mid_price - b_margin_t))
        our_ask_t = int(round(mid_price + s_margin_t))

        pos_for_buys = current_pos
        for ask_price in sorted(order_depth.sell_orders.keys()):
            if ask_price <= our_bid_t:
                available_vol = -order_depth.sell_orders[ask_price]
                max_buy = global_limit - pos_for_buys
                if max_buy <= 0:
                    break
                buy_vol = min(available_vol, max_buy)
                orders.append(Order(product, ask_price, buy_vol))
                pos_for_buys += buy_vol
            else:
                break

        pos_for_sells = current_pos
        for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if bid_price >= our_ask_t:
                available_vol = order_depth.buy_orders[bid_price]
                max_sell = pos_for_sells - (-global_limit)
                if max_sell <= 0:
                    break
                sell_vol = min(available_vol, max_sell)
                orders.append(Order(product, bid_price, -sell_vol))
                pos_for_sells -= sell_vol
            else:
                break

        highest_bid, highest_bid_volume, lowest_ask, lowest_ask_volume = (
            self.get_middest_bid_ask(state, product, orders)
        )
        if highest_bid!=None and highest_bid_volume <= params["IGNORE_TRADES_VALUE"]:
            highest_bid -= 1
        if lowest_ask!=None and lowest_ask_volume >= -params["IGNORE_TRADES_VALUE"]:
            lowest_ask += 1

        mm_buy_room = global_limit - pos_for_buys
        if mm_buy_room > 0:
            newest_order = None
            if highest_bid != None and (highest_bid + 1) < mid_price:
                newest_order = Order(product, int(highest_bid + 1), mm_buy_room)
            else:
                newest_order = Order(product, int(mid_price - params["MAKER_MARGIN"]), mm_buy_room)
            orders.append(newest_order)
            pos_for_buys += orders[-1].quantity

        mm_sell_room = pos_for_sells - (-global_limit)
        if mm_sell_room > 0:
            newest_order = None
            if lowest_ask != None and (lowest_ask - 1) > mid_price:
                newest_order = Order(product, int(lowest_ask - 1), -mm_sell_room)
            else:
                newest_order = Order(product, int(mid_price + params["MAKER_MARGIN"]), -mm_sell_room)
            orders.append(newest_order)
            pos_for_sells += orders[-1].quantity

        return orders, new_trader_data

    def run(self, state: TradingState):
        """Extracts the traderData for the different assets. Calls their respective functions and merges the orders and the new tradeData"""
        pepper_data = ""
        osmium_data = ""

        if state.traderData:
            parts = state.traderData.split("\x1e")
            if len(parts) == 2:
                pepper_data, osmium_data = parts
            else:
                pepper_data = state.traderData

        result = {}
        new_pepper_data = pepper_data
        new_osmium_data = osmium_data

        if "INTARIAN_PEPPER_ROOT" in state.order_depths:
            pepper_orders, new_pepper_data = self.trade_pepper(state, pepper_data)
            result["INTARIAN_PEPPER_ROOT"] = pepper_orders

        if "ASH_COATED_OSMIUM" in state.order_depths:
            osmium_orders, new_osmium_data = self.trade_osmium(state, osmium_data)
            result["ASH_COATED_OSMIUM"] = osmium_orders

        final_trader_data = f"{new_pepper_data}\x1e{new_osmium_data}"
        conversions = 0
        return result, conversions, final_trader_data