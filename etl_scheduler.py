#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL Scheduler for Weekly Player Data Updates
Orchestrates transfer reconciliation and appearances updates
"""

import schedule
import time
import logging
import json
from datetime import datetime
from etl_transfer_reconciliation import TransferReconciler
from etl_appearances_updater import AppearancesUpdater

LOG = logging.getLogger(__name__)

class ETLScheduler:
    def __init__(self):
        self.transfer_reconciler = TransferReconciler()
        self.appearances_updater = AppearancesUpdater()
        
    def run_weekly_transfer_check(self):
        """Run weekly transfer reconciliation"""
        try:
            LOG.info("Starting scheduled transfer reconciliation...")
            result = self.transfer_reconciler.run_reconciliation()
            LOG.info(f"Transfer reconciliation completed: {result.get('transferred_out', 0)} players updated")
            return result
        except Exception as e:
            LOG.error(f"Transfer reconciliation failed: {e}")
            return {"error": str(e)}
    
    def run_weekly_appearances_update(self):
        """Run weekly appearances update"""
        try:
            LOG.info("Starting scheduled appearances update...")
            result = self.appearances_updater.run_weekly_update()
            LOG.info(f"Appearances update completed: {result.get('updated_players', 0)} players updated")
            return result
        except Exception as e:
            LOG.error(f"Appearances update failed: {e}")
            return {"error": str(e)}
    
    def run_full_weekly_update(self):
        """Run complete weekly update"""
        LOG.info("=== Starting Weekly Player Data Update ===")
        
        # Run transfer reconciliation first
        transfer_result = self.run_weekly_transfer_check()
        
        # Then update appearances
        appearances_result = self.run_weekly_appearances_update()
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "transfer_reconciliation": transfer_result,
            "appearances_update": appearances_result,
            "success": "error" not in transfer_result and "error" not in appearances_result
        }
        
        LOG.info("=== Weekly Player Data Update Complete ===")
        return summary
    
    def setup_schedule(self):
        """Setup automated scheduling"""
        # Run transfer reconciliation every Sunday at 2 AM
        schedule.every().sunday.at("02:00").do(self.run_weekly_transfer_check)
        
        # Run appearances update every Monday at 3 AM (after matches)
        schedule.every().monday.at("03:00").do(self.run_weekly_appearances_update)
        
        # Run full update every Tuesday at 1 AM
        schedule.every().tuesday.at("01:00").do(self.run_full_weekly_update)
        
        LOG.info("ETL schedule configured:")
        LOG.info("- Transfer check: Every Sunday 2:00 AM")
        LOG.info("- Appearances update: Every Monday 3:00 AM") 
        LOG.info("- Full update: Every Tuesday 1:00 AM")
    
    def run_daemon(self):
        """Run scheduler daemon"""
        self.setup_schedule()
        LOG.info("ETL Scheduler daemon started")
        
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

def manual_update():
    """Manual trigger for immediate update"""
    scheduler = ETLScheduler()
    result = scheduler.run_full_weekly_update()
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    if len(sys.argv) > 1 and sys.argv[1] == "manual":
        manual_update()
    else:
        scheduler = ETLScheduler()
        scheduler.run_daemon()