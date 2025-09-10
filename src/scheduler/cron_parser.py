"""Cron expression parsing and validation."""

from croniter import croniter
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def validate_cron(expression: str) -> bool:
    """Validate a cron expression.
    
    Args:
        expression: Cron expression string (e.g., "0 */2 * * *")
    
    Returns:
        True if valid, False otherwise
    """
    try:
        croniter(expression)
        return True
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid cron expression '{expression}': {e}")
        return False


def parse_cron_expression(expression: str, base_time: Optional[datetime] = None) -> Optional[datetime]:
    """Parse cron expression and get next execution time.
    
    Args:
        expression: Cron expression string
        base_time: Base time for calculation (default: now)
    
    Returns:
        Next execution datetime or None if invalid
    """
    try:
        base = base_time or datetime.utcnow()
        cron = croniter(expression, base)
        next_time = cron.get_next(datetime)
        return next_time
    except (ValueError, TypeError) as e:
        logger.error(f"Failed to parse cron expression '{expression}': {e}")
        return None


def get_cron_description(expression: str) -> str:
    """Get human-readable description of cron expression.
    
    Args:
        expression: Cron expression string
    
    Returns:
        Human-readable description
    """
    # Common patterns
    patterns = {
        "* * * * *": "Every minute",
        "*/5 * * * *": "Every 5 minutes",
        "*/10 * * * *": "Every 10 minutes",
        "*/15 * * * *": "Every 15 minutes",
        "*/30 * * * *": "Every 30 minutes",
        "0 * * * *": "Every hour",
        "0 */2 * * *": "Every 2 hours",
        "0 */4 * * *": "Every 4 hours",
        "0 */6 * * *": "Every 6 hours",
        "0 */12 * * *": "Every 12 hours",
        "0 0 * * *": "Daily at midnight",
        "0 6 * * *": "Daily at 6:00 AM",
        "0 12 * * *": "Daily at noon",
        "0 18 * * *": "Daily at 6:00 PM",
        "0 0 * * 0": "Weekly on Sunday at midnight",
        "0 0 * * 1": "Weekly on Monday at midnight",
        "0 0 * * 5": "Weekly on Friday at midnight",
        "0 0 1 * *": "Monthly on the 1st at midnight",
        "0 0 15 * *": "Monthly on the 15th at midnight",
        "0 0 1 1 *": "Yearly on January 1st at midnight",
    }
    
    if expression in patterns:
        return patterns[expression]
    
    # Try to parse and describe
    try:
        parts = expression.split()
        if len(parts) != 5:
            return expression
        
        minute, hour, day, month, weekday = parts
        
        # Build description
        desc_parts = []
        
        if minute != "*":
            if minute.startswith("*/"):
                desc_parts.append(f"every {minute[2:]} minutes")
            else:
                desc_parts.append(f"at minute {minute}")
        
        if hour != "*":
            if hour.startswith("*/"):
                desc_parts.append(f"every {hour[2:]} hours")
            else:
                desc_parts.append(f"at hour {hour}")
        
        if day != "*":
            desc_parts.append(f"on day {day}")
        
        if month != "*":
            months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            try:
                month_idx = int(month) - 1
                if 0 <= month_idx < 12:
                    desc_parts.append(f"in {months[month_idx]}")
                else:
                    desc_parts.append(f"in month {month}")
            except:
                desc_parts.append(f"in month {month}")
        
        if weekday != "*":
            days = ["Sunday", "Monday", "Tuesday", "Wednesday", 
                   "Thursday", "Friday", "Saturday"]
            try:
                day_idx = int(weekday)
                if 0 <= day_idx <= 6:
                    desc_parts.append(f"on {days[day_idx]}")
                else:
                    desc_parts.append(f"on weekday {weekday}")
            except:
                desc_parts.append(f"on weekday {weekday}")
        
        if desc_parts:
            return "Runs " + ", ".join(desc_parts)
        else:
            return "Every minute"
            
    except Exception as e:
        logger.debug(f"Could not describe cron expression '{expression}': {e}")
        return expression