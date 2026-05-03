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

    CONFIG = { # The only change between Rounds 3 and 4 was a change in the config, to lower mean prices for the options
        "VELVETFRUIT_EXTRACT": {
            "LIMIT": 200,
            "AVERAGE_SPREAD": 6,
            "VOL_FOR_WALL": 40,
            "AVERAGE_PRICE": 5250,
            "GO_FULL": 30,
            "GO_DEVIATION": 20,
            "START_PERC": 0.7,
            "SMALL_DELTA": -2,
        },
        "HYDROGEL_PACK": {
            "LIMIT": 200,
            "AVERAGE_SPREAD": 21,
            "VOL_FOR_WALL": 20,
            "AVERAGE_PRICE": 9991,
            "GO_FULL": 45,
            "GO_DEVIATION": 20,
            "START_PERC": 0.3,
            "SMALL_DELTA": 0,
        },
        "VEV_4000": {
            "LIMIT": 300,
            "AVERAGE_SPREAD": 26,
            "VOL_FOR_WALL": 15,
            "AVERAGE_PRICE": 1250,
            "GO_FULL": 35,
            "GO_DEVIATION": 17,
            "START_PERC": 0.5,
            "SMALL_DELTA": -4,
        },
        "VEV_4500": {
            "LIMIT": 300,
            "AVERAGE_SPREAD": 19,
            "VOL_FOR_WALL": 15,
            "AVERAGE_PRICE": 750,
            "GO_FULL": 30,
            "GO_DEVIATION": 17,
            "START_PERC": 0.5,
            "SMALL_DELTA": 0,
        },
        "VEV_5000": {
            "LIMIT": 300,
            "AVERAGE_SPREAD": 7,
            "VOL_FOR_WALL": 15,
            "AVERAGE_PRICE": 250,
            "GO_FULL": 30,
            "GO_DEVIATION": 17,
            "START_PERC": 0.5,
            "SMALL_DELTA": -3,
        },
        "VEV_5100": {
            "LIMIT": 300,
            "AVERAGE_SPREAD": 5,
            "VOL_FOR_WALL": 15,
            "AVERAGE_PRICE": 160,
            "GO_FULL": 30,
            "GO_DEVIATION": 15,
            "START_PERC": 0.5,
            "SMALL_DELTA": -3,
        },
        "VEV_5200": {
            "LIMIT": 300,
            "AVERAGE_SPREAD": 3,
            "VOL_FOR_WALL": 15,
            "AVERAGE_PRICE": 88,
            "GO_FULL": 25,
            "GO_DEVIATION": 8,
            "START_PERC": 0.5,
            "SMALL_DELTA": -2,
        },
        "VEV_5300": {
            "LIMIT": 300,
            "AVERAGE_SPREAD": 2,
            "VOL_FOR_WALL": 0,
            "AVERAGE_PRICE": 39,
            "GO_FULL": 15,
            "GO_DEVIATION": 5,
            "START_PERC": 0.5,
            "SMALL_DELTA": -1,
        },
        "VEV_5400": {
            "LIMIT": 300,
            "AVERAGE_SPREAD": 1,
            "VOL_FOR_WALL": 0,
            "AVERAGE_PRICE": 12,
            "GO_FULL": 8,
            "GO_DEVIATION": 3,
            "START_PERC": 0.5,
            "SMALL_DELTA": 0,
        },
        "VEV_5500": {
            "LIMIT": 300,
            "AVERAGE_SPREAD": 2,
            "VOL_FOR_WALL": 0,
            "AVERAGE_PRICE": 1,
            "GO_FULL": 5,
            "GO_DEVIATION": 1,
            "START_PERC": 0.4,
            "SMALL_DELTA": 0,
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
            previous_price = params["AVERAGE_PRICE"]
        # calculating actual_price
        ask_wall = -1
        for ask_price, vol in order_depth.sell_orders.items():
            if vol < -params["VOL_FOR_WALL"]:
                ask_wall = max(ask_price,ask_wall)
        bid_wall = -1
        for bid_price, vol in order_depth.buy_orders.items():
            if vol > params["VOL_FOR_WALL"]:
                if bid_wall==-1: 
                    bid_wall = bid_price
                else: bid_wall = min(bid_wall,bid_price)
        if bid_wall != -1 and ask_wall == -1:
            ask_wall = bid_wall + params["AVERAGE_SPREAD"]
        elif bid_wall == -1 and ask_wall != -1:
            bid_wall = ask_wall - params["AVERAGE_SPREAD"]
        if ask_wall == -1:
            actual_price = previous_price
        else:
            actual_price = (bid_wall + ask_wall) / 2
        mid_price = int(actual_price)
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

    def trade_mean_reverting(self, state: TradingState, trader_data: str, product : str):
        order_depth: OrderDepth = state.order_depths[product]
        orders: List[Order] = []
        params = self.CONFIG[product]
        new_trader_data: str = trader_data

        global_limit = params['LIMIT']
        current_pos = state.position.get(product, 0)
        
        # STRATEGY EXPLANATION
        # I try to use the mean reverting nature of hydrogel and the kinda mean reverting nature of velvefruit and 
        # the options that mimic its price. The main idea of a mean reverting asset is that it follows a mean price, only
        # flunctuating around it through some random noice. So if it is far from the random noise, you can expect it to return
        # So the basic idea is to hold a lot, when the price is low, and hold very few when it is much.
        # The exact implementation is as follows. I have a fixed average_price, and a fixed range
        # [go_dev, go_full]. When the price of a bid gets inside of the range average_price + [go_dev, go_full]
        # this is a signal to sell. The exact quantity is that for each price in the range I try to hold a certain position
        # I have fitted a linear function ax+b, which means that we want to hold 100% when price is at + go_full (or higher),
        # and hold START_PERC (depends on product) at +go_dev. What ends up happening is we gradually buy during a hill.
        # Then I sell when the price of an ask hits average_price + small_delta (depends on product), 
        # so I dont wait for the full swing, I take my safe money when possible. Codewise this means, buy until we are at
        # exactly 0 position.  The logic for asks is the same but for low prices and buying. The same function is used.
        # I also implemented adding maker offers at the mid_price with exactly these rules. I see that a lot of bots 
        # are buying historically, so I hope I can buy better with less paying of the spread

        # Note on solution. Hitting a good mean price is very key for profit. We werent able to hit a good mean price for the 
        # last 3 options and lost around 1k pnl on each, while further testing with different mean prices showed potential
        # of generating around +70k pnl on Round 3 if we had chosen better prices.
          
        mid_price = self.wall_mid_price(order_depth,trader_data,params)

        linear_a = (1-params["START_PERC"]) / (params["GO_FULL"]-params["GO_DEVIATION"])
        linear_b = 1 - linear_a*params["GO_FULL"]
        pos_for_buy = current_pos
        pos_for_sell = current_pos
        for ask_price, vol in sorted(order_depth.sell_orders.items()):
            if ask_price < params["AVERAGE_PRICE"] - params["GO_DEVIATION"]:
                price_coeff = min((params["AVERAGE_PRICE"]-ask_price),params["GO_FULL"]) * linear_a + linear_b
                quantity = min ( (global_limit*price_coeff - pos_for_buy) , -vol )
                if quantity < 0: continue
                quantity = int(quantity)
                orders.append(Order(product,ask_price,quantity))
                pos_for_buy += quantity
            elif ask_price < params["AVERAGE_PRICE"] + params["SMALL_DELTA"] and pos_for_buy<0:
                quantity = min(-pos_for_buy , -vol)
                orders.append(Order(product,ask_price,quantity))
                pos_for_buy += quantity
        for bid_price, vol in sorted(order_depth.buy_orders.items(), reverse=True):
            if bid_price > params["AVERAGE_PRICE"] + params["GO_DEVIATION"]:
                price_coeff = min((bid_price - params["AVERAGE_PRICE"]),params["GO_FULL"]) * linear_a + linear_b
                quantity = min( (pos_for_sell + global_limit*price_coeff), vol )
                if quantity < 0: continue
                quantity = int(quantity)
                orders.append(Order(product,bid_price,-quantity))
                pos_for_sell -= quantity
            elif bid_price > params["AVERAGE_PRICE"] - params["SMALL_DELTA"] and pos_for_sell>0:
                quantity = min(pos_for_sell, vol)
                orders.append(Order(product,bid_price,-quantity))
                pos_for_sell -= quantity
        
        if params["VOL_FOR_WALL"]!=0:
            if mid_price < params["AVERAGE_PRICE"] - params["GO_DEVIATION"]:
                price_coeff = min((params["AVERAGE_PRICE"]-mid_price),params["GO_FULL"]) * linear_a + linear_b
                quantity = (global_limit*price_coeff - pos_for_buy)
                if quantity >= 0:
                    quantity = int(quantity)
                    orders.append(Order(product,mid_price,quantity))
                    pos_for_buy += quantity
            elif mid_price < params["AVERAGE_PRICE"] + params["SMALL_DELTA"] and pos_for_buy<0:
                quantity = -pos_for_buy
                orders.append(Order(product,mid_price,quantity))
                pos_for_buy += quantity
            elif pos_for_buy<0 and (mid_price - (params["AVERAGE_PRICE"]+params["SMALL_DELTA"])) < params["AVERAGE_SPREAD"]/2:
                quantity = -pos_for_buy
                orders.append(Order(product,params["AVERAGE_PRICE"]+params["SMALL_DELTA"],quantity))
            if mid_price > params["AVERAGE_PRICE"] + params["GO_DEVIATION"]:
                price_coeff = min((bid_price - params["AVERAGE_PRICE"]),params["GO_FULL"]) * linear_a + linear_b
                quantity = (pos_for_sell + global_limit*price_coeff)
                if quantity >= 0:
                    quantity = int(quantity)
                    orders.append(Order(product,mid_price,-quantity))
                    pos_for_sell -= quantity
            elif mid_price > params["AVERAGE_PRICE"] - params["SMALL_DELTA"] and pos_for_sell>0:
                quantity = pos_for_sell
                orders.append(Order(product,mid_price,-quantity))
                pos_for_sell -= quantity
            elif pos_for_sell>0 and (params["AVERAGE_PRICE"] - params["SMALL_DELTA"] - mid_price) < params["AVERAGE_SPREAD"]/2:
                quantity = pos_for_sell
                orders.append(Order(product,params["AVERAGE_PRICE"]-params["SMALL_DELTA"],-quantity))
                pos_for_sell -= quantity
        new_trader_data = str(mid_price)
        return orders, new_trader_data

    def run(self, state: TradingState):
        """Extracts the traderData for the different assets. Calls their respective functions and merges the orders and the new tradeData"""        
        hydro_data, velve_data, ta_data ,t0_data, t1_data, t2_data, t3_data, t4_data, t5_data, t6_data = ('','','','','','','','','','')
        if state.traderData:
            parts = state.traderData.split("\x1e")
            if len(parts) == 10:
                hydro_data, velve_data, ta_data, t0_data, t1_data, t2_data, t3_data, t4_data, t5_data, t6_data = parts

        result = {}
        new_hydro_data = hydro_data
        new_velve_data = velve_data

        if "HYDROGEL_PACK" in state.order_depths:
            hydro_orders, new_hydro_data = self.trade_mean_reverting(state, hydro_data, "HYDROGEL_PACK")
            result["HYDROGEL_PACK"] = hydro_orders

        if "VELVETFRUIT_EXTRACT" in state.order_depths:
            velve_orders, new_velve_data = self.trade_mean_reverting(state, velve_data, "VELVETFRUIT_EXTRACT")
            result["VELVETFRUIT_EXTRACT"] = velve_orders

        if "VEV_4000" in state.order_depths:
            ordersa, new_dataa = self.trade_mean_reverting(state, ta_data,"VEV_4000")
            result["VEV_4000"] = ordersa

        if "VEV_4500" in state.order_depths:
            orders0, new_data0 = self.trade_mean_reverting(state, t0_data,"VEV_4500")
            result["VEV_4500"] = orders0

        if "VEV_5000" in state.order_depths:
            orders1, new_data1 = self.trade_mean_reverting(state, t1_data,"VEV_5000")
            result["VEV_5000"] = orders1

        if "VEV_5100" in state.order_depths:
            orders2, new_data2 = self.trade_mean_reverting(state, t2_data, "VEV_5100")
            result["VEV_5100"] = orders2

        if "VEV_5200" in state.order_depths:
            orders3, new_data3 = self.trade_mean_reverting(state, t3_data, "VEV_5200")
            result["VEV_5200"] = orders3

        if "VEV_5300" in state.order_depths:
            orders4, new_data4 = self.trade_mean_reverting(state, t4_data, "VEV_5300")
            result["VEV_5300"] = orders4

        if "VEV_5400" in state.order_depths:
            orders5, new_data5 = self.trade_mean_reverting(state, t5_data, "VEV_5400")
            result["VEV_5400"] = orders5

        if "VEV_5500" in state.order_depths:
            orders6, new_data6 = self.trade_mean_reverting(state, t6_data, "VEV_5500")
            result["VEV_5500"] = orders6

        final_trader_data = f"{new_hydro_data}\x1e{new_velve_data}\x1e{new_dataa}\x1e{new_data0}"
        final_trader_data+= f"\x1e{new_data1}\x1e{new_data2}\x1e{new_data3}\x1e{new_data4}"
        final_trader_data+=f'\x1e{new_data5}\x1e{new_data6}'
        conversions = 0
        return result, conversions, final_trader_data