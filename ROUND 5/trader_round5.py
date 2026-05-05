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
import json
import math


class Trader:

    CONFIG = {
        "SLEEP": {"DIP_PRICE": 1500, "LIMIT": 10},
        "PANELS": {
            "TIMESTAMP_WAIT": 400000,
            "GO_DEV": 1000,
            "START_WIND": 300,
            "SAFE_WIND": 50,
            "DESPERATE_SELL": 150000,
            "LIMIT": 10,
            "WINDOW": 100,
            "ENTRY_Z": 2,
            "EXIT_Z": 1.2,
        },
        "PEBBLES": {
            "LIMIT": 10,
        },
        "SNACKPACK": {
            "LIMIT": 10,
        },
        "OXYGEN": {
            "LIMIT": 10,
            "WINDOW": 50,
            "ENTRY_Z": 2,
            "EXIT_Z": 1.2,
        },
        "GALAXY": {
            "LIMIT": 10,
            "WINDOW": 30,
            "ENTRY_Z": 2,
            "EXIT_Z": 1.2,
        },
        "MICROCHIP": {
            "TIMESTAMP_WAIT": 400000,
            "GO_DEV": 1000,
            "START_WIND": 300,
            "SAFE_WIND": 50,
            "DESPERATE_SELL": 150000,
            "LIMIT": 10,
            "WINDOW": 150,
            "ENTRY_Z": 2,
            "EXIT_Z": 1.2,
        },
        "ROBOT": {
            "AVERAGE_PRICE": 39000,
            "START_PERC": 0.7,
            "GO_FULL": 1000,
            "GO_DEVIATION": 500,
            "SMALL_DELTA": 20,
            "LIMIT": 10,
        },
        "UV": {
            "TIMESTAMP_WAIT": 200000,
            "GO_DEV": 1000,
            "START_WIND": 300,
            "SAFE_WIND": 50,
            "DESPERATE_SELL": 150000,
            "LIMIT": 10,
            "WINDOW": 30,
            "ENTRY_Z": 2,
            "EXIT_Z": 1,
        },
        "Translator": {"DIP_PRICE": 1500, "LIMIT": 10},
    }

    def wall_mid_price(self, order_depth: OrderDepth) -> float:
        """Function implementing the wall_mid algorithm modified for prosperity4. Returns None if unable"""
        # MID_PRICE
        # Explanation: I implement Frankfurt's Wall Mid which is average of the two high-volume orders.
        # However this year, commonly there are days without one of the big offers, so I just make it up by
        # adding/removing the average_spread when only one is present.
        #  When neither is present, i just use the previous price which is stored in traderData
        ask_wall = -1
        for ask_price, vol in order_depth.sell_orders.items():
            ask_wall = max(ask_price, ask_wall)
        bid_wall = -1
        for bid_price, vol in order_depth.buy_orders.items():
            if bid_wall == -1:
                bid_wall = bid_price
            else:
                bid_wall = min(bid_wall, bid_price)
        if bid_wall != -1 and ask_wall == -1:
            return None
        elif bid_wall == -1 and ask_wall != -1:
            return None
        if ask_wall == -1:
            return None
        else:
            actual_price = (bid_wall + ask_wall) / 2
        mid_price = int(actual_price)
        return mid_price

    def get_middest_bid_ask(
        self, state: TradingState, product: str, current_orders: List[Order]
    ):
        """Receives a list of orders the strategy has done so far. It returns the highest bid and lowest ask, still on the market"""
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

    def trade_to_position(
        self,
        state: TradingState,
        product: str,
        position: int,
    ):
        """Trades single item by buying or selling everything with the goal of getting to the given position"""
        # An important detail is that the function doesnt allow you to lower your position when its positive, or increase
        # it when it is negative, unless you are specifically making it 0. This was done to make the mean_reverting_group code
        # easier, so it doesnt constantly check what the positions are and if it should actually do trades.
        order_depth: OrderDepth = state.order_depths[product]
        orders: List[Order] = []
        current_pos = state.position.get(product, 0)
        pos_for_buy = current_pos
        pos_for_sell = current_pos
        for ask_price, vol in sorted(order_depth.sell_orders.items()):
            if pos_for_buy < position and (position >= 0):
                quantity = min(position - pos_for_buy, -vol)
                orders.append(Order(product, ask_price, quantity))
                pos_for_buy += quantity
        for bid_price, vol in sorted(order_depth.buy_orders.items(), reverse=True):
            if pos_for_sell > position and (position <= 0):
                quantity = min(pos_for_sell - position, vol)
                orders.append(Order(product, bid_price, -quantity))
                pos_for_sell -= quantity
        return orders

    def trade_mean_reverting_group(
        self, state: TradingState, trader_data: str, product: str, all_products
    ) -> tuple[Dict[str, List[Order]], str]:
        orders: Dict[str, List[Order]] = {}
        params = self.CONFIG[product]
        # STRATEGY EXPLANATION
        # This strategy is only used for a group of 4 robot products, which behaved extremely mean revertingly in the given data
        # It is really similar to the rounds 3 and 4 strategys. Except for using the price of an offer to determine the position
        # this strategy just uses the current wall_mid of the etf. After determining what position it wants to hold, it calls
        # the trade_to_position function for each asset, which does the actual trades.
        # Main details are still sell at + [GO_DEVIATION,GO_FULL] and buy at - [GO_DEVIATION,GO_FULL] and empty close to the
        # average price
        sum_mid_price = 0
        for names in all_products:
            mid_price = self.wall_mid_price(state.order_depths[names])
            if mid_price is None:
                return {}, ""
            sum_mid_price += mid_price
        trader_data = str(sum_mid_price)
        desired_volume = None
        linear_a = (1 - params["START_PERC"]) / (
            params["GO_FULL"] - params["GO_DEVIATION"]
        )
        linear_b = 1 - linear_a * params["GO_FULL"]
        if sum_mid_price > params["AVERAGE_PRICE"] + params["GO_DEVIATION"]:
            howm = min(sum_mid_price - params["AVERAGE_PRICE"], params["GO_FULL"])
            desired_volume = (linear_a * howm + linear_b) * -1 * params["LIMIT"]
        elif sum_mid_price < params["AVERAGE_PRICE"] - params["GO_DEVIATION"]:
            howm = min(params["AVERAGE_PRICE"] - sum_mid_price, params["GO_FULL"])
            desired_volume = (linear_a * howm + linear_b) * params["LIMIT"]
        elif (
            sum_mid_price >= params["AVERAGE_PRICE"] - params["SMALL_DELTA"]
            and sum_mid_price <= params["AVERAGE_PRICE"] + params["SMALL_DELTA"]
        ):
            desired_volume = 0
        if desired_volume is None:
            return {}, trader_data
        desired_volume = int(desired_volume)
        for names in all_products:
            orders[names] = self.trade_to_position(state, names, desired_volume)
        return orders, trader_data

    def trade_sleep(self, state: TradingState, trader_data: str):
        """Trades Sleep"""
        params = self.CONFIG["SLEEP"]
        all_products = [
            "SLEEP_POD_SUEDE",
            "SLEEP_POD_LAMB_WOOL",
            "SLEEP_POD_POLYESTER",
            "SLEEP_POD_NYLON",
            "SLEEP_POD_COTTON",
        ]
        # STRATEGY EXPLANATION
        # The sleep strategy is really dumb and risky. We observed a stable growth in the asset. To use it, we
        # buy immediately to max position, and sell to 0 when the price gets more than buy_price + DIP_PRICE for an overall
        # of 10 * DIP_PRICE profit. This strategy was mainly brought on by the fact that we wanted to trade everything
        orders = {}
        if state.timestamp <= 1000:
            sum_mid_price = 0
            for names in all_products:
                mid_price = self.wall_mid_price(state.order_depths[names])
                if mid_price is None:
                    mid_price = None
                    break
                sum_mid_price += mid_price
            if sum_mid_price is not None and not trader_data:
                trader_data = str(sum_mid_price)
            for names in all_products:
                orders[names] = self.trade_to_position(state, names, params["LIMIT"])
        else:
            sum_mid_price = 0
            for names in all_products:
                mid_price = self.wall_mid_price(state.order_depths[names])
                if mid_price is None:
                    return {}, ""
                sum_mid_price += mid_price
            if sum_mid_price - int(trader_data) >= params["DIP_PRICE"]:
                for names in all_products:
                    orders[names] = self.trade_to_position(state, names, 0)
        return orders, trader_data

    def trade_translator(self, state: TradingState, trader_data: str):
        """Trades Translator"""
        params = self.CONFIG["Translator"]
        all_products = [
            "TRANSLATOR_SPACE_GRAY",
            "TRANSLATOR_ASTRO_BLACK",
            "TRANSLATOR_ECLIPSE_CHARCOAL",
            "TRANSLATOR_GRAPHITE_MIST",
            "TRANSLATOR_VOID_BLUE",
        ]
        # STRATEGY EXPLANATION
        # The translator strategy is really dumb and risky. We observed a really flanky price movement of the translator.
        # Where it would go down a lot, then back up. To use it, we sell immediately to max position, and buy to 0 when the
        # price gets more than buy_price + DIP_PRICE for an overall of 10 * DIP_PRICE profit.
        # Another distiction is that we added a 100k timestamp wait for the start selling, since day 4 had ended on a relatively
        # small price and we expected an increase in the price
        # This strategy was mainly brought on by the fact that we wanted to trade everything
        orders = {}
        if state.timestamp <= 100000:
            return {}, trader_data
        if state.timestamp <= 101000:
            sum_mid_price = 0
            for names in all_products:
                mid_price = self.wall_mid_price(state.order_depths[names])
                if mid_price is None:
                    mid_price = None
                    break
                sum_mid_price += mid_price
            if sum_mid_price is not None and not trader_data:
                trader_data = str(sum_mid_price)
            for names in all_products:
                orders[names] = self.trade_to_position(state, names, -params["LIMIT"])
        else:
            sum_mid_price = 0
            for names in all_products:
                mid_price = self.wall_mid_price(state.order_depths[names])
                if mid_price is None:
                    return {}, ""
                sum_mid_price += mid_price
            if int(trader_data) - sum_mid_price >= params["DIP_PRICE"]:
                for names in all_products:
                    orders[names] = self.trade_to_position(state, names, 0)
        return orders, trader_data

    def trade_maker_with_limits(
        self, state: TradingState, product: str, min_allowed: int, max_allowed: int
    ) -> List[Order]:
        """Trades market maker a single product with limits given for min position allowed and max position allowed"""
        position = state.position.get(product, 0)
        order_depth: OrderDepth = state.order_depths[product]
        orders: List[Order] = []
        highest_bid, highest_bid_volume, lowest_ask, lowest_ask_volume = (
            self.get_middest_bid_ask(state, product, [])
        )
        if highest_bid != None:
            volume = max_allowed - position
            assert volume >= 0
            orders.append(Order(product, highest_bid + 1, volume))
        if lowest_ask != None:
            volume = position - min_allowed
            assert volume >= 0
            orders.append(Order(product, lowest_ask - 1, -volume))
        return orders

    def trade_market_making_group(
        self, state: TradingState, trader_data: str, product: str, all_products: list
    ) -> tuple[Dict[str, List[Order]], str]:
        """Trades a group of products as a market making etf"""
        params = self.CONFIG[product]
        # STRATEGY EXPLANATION
        # This strategy is used for Pebbles and Snackpack. We observed a really stable group price (pebbles is constant,
        # snackpack moves by less than 200). Also we observed that a single buyer was selling or buying all of them at the same
        # price, so we could think of them as a really stable ETF.
        # We market make this etf, by putting offers at the highest_bid + 1 and lowest_ask - 1.
        # The exact offers are placed by the trade_maker_with_limits function for each product in the etf
        max_allowed = params["LIMIT"]
        min_allowed = -params["LIMIT"]
        orders = {}
        for name in all_products:
            orders[name] = self.trade_maker_with_limits(
                state, name, min_allowed, max_allowed
            )
        return orders, trader_data

    def trade_z_score(
        self,
        state: TradingState,
        product: str,
        products: list,
        trader_data: str,
    ) -> tuple[Dict[str, List[Order]], str]:
        mids: Dict[str, int] = {}
        current_sum = 0
        params = self.CONFIG[product]

        # STRATEGY EXPLANATION
        # This strategy implements a mean-reversion z-score model on a group of products.
        # At each step, it computes the mid-price for each product and sums them to form the group price.
        # It maintains a rolling window of the group price over the last WINDOW steps, from which it calculates the rolling mean and standard deviation.
        # The z-score is then computed as the deviation of the current group price from the rolling mean, normalized by the standard deviation.
        # If the z-score exceeds ENTRY_Z, the strategy sells
        # If the z-score is below -ENTRY_Z, the strategy buys=
        # If positions are already open and the z-score reverts within [-EXIT_Z, EXIT_Z], the strategy closes positions

        for product in products:
            if product not in state.order_depths:
                return {}, trader_data
            mid_price = self.wall_mid_price(state.order_depths[product])
            mids[product] = mid_price
            current_sum += mids[product]

        state_dict: Dict[str, Any] = {}
        if trader_data:
            state_dict = json.loads(trader_data)

        raw_history = state_dict.get("sum_history", [])
        sum_history: List[float] = []
        for value in raw_history:
            sum_history.append(float(value))

        sum_history.append(float(current_sum))
        window = int(params["WINDOW"])
        if len(sum_history) > window:
            sum_history = sum_history[-window:]

        rolling_mean = sum(sum_history) / len(sum_history)
        variance = sum((x - rolling_mean) ** 2 for x in sum_history) / len(sum_history)
        rolling_std = math.sqrt(variance)
        z_score = 0.0
        if rolling_std >= 1e-9:
            z_score = (current_sum - rolling_mean) / rolling_std

        desired_volume = None
        entry_z = float(params["ENTRY_Z"])
        exit_z = float(params["EXIT_Z"])
        current_positions = [state.position.get(product, 0) for product in products]
        holding = any(pos != 0 for pos in current_positions)

        if len(sum_history) >= window:
            if z_score > entry_z:
                desired_volume = -int(params["LIMIT"])
            elif z_score < -entry_z:
                desired_volume = int(params["LIMIT"])
            elif holding and -exit_z <= z_score <= exit_z:
                desired_volume = 0

        max_allowed = params["LIMIT"]
        min_allowed = -params["LIMIT"]

        orders: Dict[str, List[Order]] = {}
        if desired_volume is not None:
            for product in products:
                orders[product] = self.trade_maker_with_limits(
                    state, product, min_allowed, max_allowed
                )

        state_dict["sum_history"] = sum_history
        return orders, json.dumps(state_dict)

    def run(self, state: TradingState):
        """Extracts the traderData for the different assets. Calls their respective functions and merges the orders and the new tradeData"""
        (
            t0_data,
            t1_data,
            t2_data,
            t3_data,
            t4_data,
            t5_data,
            t6_data,
            t7_data,
            t8_data,
            t9_data,
        ) = ("", "", "", "", "", "", "", "", "", "")
        if state.traderData:
            parts = state.traderData.split("\x1e")
            if len(parts) == 10:
                (
                    t0_data,
                    t1_data,
                    t2_data,
                    t3_data,
                    t4_data,
                    t5_data,
                    t6_data,
                    t7_data,
                    t8_data,
                    t9_data,
                ) = parts

        result = {}

        # Our main Goal for Round 5 was to try and trade everything. Whatever small gains it may have, just try and trade
        # every single product

        if True:
            t0_orders, new_t0_data = self.trade_z_score(
                state,
                "PANELS",
                ["PANEL_1X2", "PANEL_2X2", "PANEL_1X4", "PANEL_2X4", "PANEL_4X4"],
                t0_data,
            )
            for key in t0_orders.keys():
                result[key] = t0_orders[key]
            t0_data = new_t0_data

        if True:
            t1_orders, new_t1_data = self.trade_sleep(state, t1_data)
            for key in t1_orders.keys():
                result[key] = t1_orders[key]
            t1_data = new_t1_data

        if True:
            t2_orders, new_t2_data = self.trade_market_making_group(
                state,
                t2_data,
                "SNACKPACK",
                [
                    "SNACKPACK_CHOCOLATE",
                    "SNACKPACK_VANILLA",
                    "SNACKPACK_PISTACHIO",
                    "SNACKPACK_STRAWBERRY",
                    "SNACKPACK_RASPBERRY",
                ],
            )
            for key in t2_orders.keys():
                result[key] = t2_orders[key]
            t2_data = new_t2_data

        if True:
            t3_orders, new_t3_data = self.trade_market_making_group(
                state,
                t3_data,
                "PEBBLES",
                ["PEBBLES_XS", "PEBBLES_S", "PEBBLES_M", "PEBBLES_L", "PEBBLES_XL"],
            )
            for key in t3_orders.keys():
                result[key] = t3_orders[key]
            t3_data = new_t3_data

        if True:
            t4_orders, new_t4_data = self.trade_z_score(
                state,
                "MICROCHIP",
                [
                    "MICROCHIP_CIRCLE",
                    "MICROCHIP_OVAL",
                    "MICROCHIP_SQUARE",
                    "MICROCHIP_RECTANGLE",
                    "MICROCHIP_TRIANGLE",
                ],
                t4_data,
            )
            for key in t4_orders.keys():
                result[key] = t4_orders[key]
            t4_data = new_t4_data

        if True:
            t5_orders, new_t5_data = self.trade_mean_reverting_group(
                state,
                t5_data,
                "ROBOT",
                ["ROBOT_VACUUMING", "ROBOT_MOPPING", "ROBOT_DISHES", "ROBOT_IRONING"],
            )
            for key in t5_orders.keys():
                result[key] = t5_orders[key]
            t5_data = new_t5_data

        if True:
            t6_orders, new_t6_data = self.trade_z_score(
                state,
                "UV",
                [
                    "UV_VISOR_YELLOW",
                    "UV_VISOR_AMBER",
                    "UV_VISOR_ORANGE",
                    "UV_VISOR_RED",
                    "UV_VISOR_MAGENTA",
                ],
                t6_data,
            )
            for key in t6_orders.keys():
                result[key] = t6_orders[key]
            t6_data = new_t6_data

        if True:
            t7_orders, new_t7_data = self.trade_translator(state, t7_data)
            for key in t7_orders.keys():
                result[key] = t7_orders[key]
            t7_data = new_t7_data

        if True:
            t8_orders, new_t8_data = self.trade_z_score(
                state,
                "OXYGEN",
                [
                    "OXYGEN_SHAKE_CHOCOLATE",
                    "OXYGEN_SHAKE_EVENING_BREATH",
                    "OXYGEN_SHAKE_GARLIC",
                    "OXYGEN_SHAKE_MINT",
                    "OXYGEN_SHAKE_MORNING_BREATH",
                ],
                t2_data,
            )
            for key in t8_orders.keys():
                result[key] = t8_orders[key]
            t2_data = new_t8_data

        if True:
            t9_orders, new_t9_data = self.trade_z_score(
                state,
                "GALAXY",
                [
                    "GALAXY_SOUNDS_DARK_MATTER",
                    "GALAXY_SOUNDS_BLACK_HOLES",
                    "GALAXY_SOUNDS_SOLAR_FLAMES",
                    "GALAXY_SOUNDS_SOLAR_WINDS",
                    "GALAXY_SOUNDS_PLANETARY_RINGS",
                ],
                t9_data,
            )
            for key in t9_orders.keys():
                result[key] = t9_orders[key]
            t9_data = new_t9_data

        final_trader_data = f"{t0_data}\x1e{t1_data}\x1e{t2_data}\x1e{t3_data}\x1e{t4_data}\x1e{t5_data}\x1e{t6_data}"
        final_trader_data += f"\x1e{t7_data}\x1e{t8_data}\x1e{t9_data}"
        conversions = 0
        return result, conversions, final_trader_data
