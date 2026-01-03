    def run(self):
        print(f"Starting Backtest: {self.start_date} to {self.end_date}")
        
        # Load Data
        master_df = self.load_all_data()
        if master_df.empty: return
        
        last_prices = {}
        last_logged_date = None
        daily_trades_viz = []
        
        for idx, row in enumerate(master_df.itertuples(index=False)):
            current_time = row.datetime
            ticker = row.market_ticker
            current_date_str = current_time.strftime("%y%b%d").upper()
            
            # --- NEW: Strict Time Filtering (Match Live Bot "Skip to End") ---
            if self.warmup_start_date and current_time < self.warmup_start_date:
                continue

            is_warmup = self.warmup_start_date and current_time < self.start_date
            
            if current_date_str != last_logged_date:
                # End of previous day logic
                if last_logged_date is not None:
                    try:
                        completed_date_obj = datetime.strptime(last_logged_date, "%y%b%d").date()
                        sweep_time = datetime.combine(completed_date_obj, datetime.min.time()) + timedelta(days=1, hours=1, minutes=5)
                        
                        daily_report = {}
                        for s in self.strategies:
                            p = self.portfolios[s.name]
                            self.handle_market_expiries(p, sweep_time, last_prices)
                            p['wallet'].check_settlements(sweep_time)
                            
                            # Snapshot
                            cash = p['wallet'].available_cash
                            unsettled = p['wallet'].unsettled_balance
                            holdings = 0
                            for src in p['inventory_yes']:
                                holdings += sum(p['inventory_yes'][src].values())
                            for src in p['inventory_no']:
                                holdings += sum(p['inventory_no'][src].values())
                            
                            equity = p['wallet'].get_total_equity()
                            
                            # Update Daily Start Equity for Next Day
                            p['daily_start_equity'] = equity
                            
                            print(f"[{last_logged_date}] {s.name} End Equity: ${equity:.2f} (Cash: ${cash:.2f}, Unsettled: ${unsettled:.2f})")
                            
                            daily_report[s.name] = {
                                'equity': equity,
                                'cash': cash,
                                'unsettled': unsettled
                            }
                            
                        # Generate Daily Chart
                        # self.generate_daily_chart(...) # Skipped for speed
                        
                    except Exception as e:
                        print(f"Error in EOD logic: {e}")

                last_logged_date = current_date_str
                print(f"Processing {current_date_str}...")
                
            # Update Market State
            market_state = {
                'yes_ask': row.implied_yes_ask,
                'no_ask': row.implied_no_ask,
                'yes_bid': row.best_yes_bid,
                'no_bid': row.best_no_bid,
                'market_ticker': ticker,
                'timestamp': current_time
            }
            
            # Update Last Prices for Settlement
            mid = (row.best_yes_bid + row.implied_yes_ask) / 2.0 if (not pd.isna(row.best_yes_bid) and not pd.isna(row.implied_yes_ask)) else np.nan
            if not pd.isna(mid):
                last_prices[ticker] = mid
            
            # Strategy Loop
            for s in self.strategies:
                p = self.portfolios[s.name]
                
                # Check Limit Fills
                self.check_limit_fills(p, ticker, market_state, current_time, daily_trades_viz, s.name, last_prices)
                
                # Get New Orders
                # Inventories: { 'YES': qty, 'NO': qty }
                inv_yes = sum(p['inventory_yes'][s.name].values()) # Simplified: assume source=strategy name for now? No, source is 'MM' etc.
                # Actually, strategy returns orders with 'source'.
                # We need to aggregate inventory by source for the strategy?
                # The strategy expects: inventories = {'YES': qty, 'NO': qty} (Total?)
                # Let's sum all sources for now.
                total_yes = sum(sum(x.values()) for x in p['inventory_yes'].values())
                total_no = sum(sum(x.values()) for x in p['inventory_no'].values())
                inventories = {'YES': total_yes, 'NO': total_no}
                
                # Active Orders
                active = p['active_limit_orders'][ticker]
                
                orders = s.on_market_update(ticker, market_state, current_time, inventories, active, p['wallet'].available_cash)
                
                if orders:
                    # Replace Active Orders
                    # But wait, on_market_update returns *new* orders to place.
                    # If it returns None, we keep existing.
                    # If it returns [], we cancel existing?
                    # The logic in Strategy says: "Returns list of dicts: New state (Replace current active orders)"
                    
                    # Cancel existing for this ticker/strategy?
                    # The strategy manages its own orders.
                    # If it returns a list, we assume these are the ONLY active orders it wants.
                    # So we clear previous active orders for this ticker.
                    
                    # But wait, we have multiple sources (MM, Scalper).
                    # The strategy returns combined orders.
                    
                    # Clear old orders for this ticker
                    p['active_limit_orders'][ticker] = []
                    
                    for o in orders:
                        # Execute Immediate (Market) or Place Limit
                        if o.get('type') == 'MARKET':
                            # Execute immediately
                            self.execute_trade(p, ticker, o['action'], o['price'], o['qty'], o['source'], current_time, market_state, s.name, daily_trades_viz)
                        else:
                            # Limit Order
                            p['active_limit_orders'][ticker].append(o)

        print("=== Backtest Complete ===")
        
        # Final Report
        print("\n=== Final Results ===")
        for s in self.strategies:
            p = self.portfolios[s.name]
            equity = p['wallet'].get_total_equity()
            roi = (equity - self.initial_capital) / self.initial_capital * 100
            print(f"{s.name}: ${equity:.2f} ({roi:.1f}%)")

if __name__ == "__main__":
    bt = ComplexBacktester()
    bt.run()
