import datetime
import ast
import click
import llm
import subprocess
import sqlite_utils
from typing import List, Optional
from click_default_group import DefaultGroup

from llm.migrations import migration, migrate
from llm.cli import get_default_model
from llm import user_dir

SUMMARY_PROMPT = """Given these calendar events, provide a natural, conversational summary:

{context}

Focus on the most important details and group related events. Be concise but friendly."""


logs_path = user_dir() / "logs.db"


SYSTEM_PROMPT = """
Available tools:
- add_entry(start_time: str, text: str, end_time: str = None, people: Optional[List] = None)
- lookup_events(start_date: str = date.today().isoformat(), end_date: str = None, people: Optional[List] = None)
- clear_events(start_date: str, end_date: str = None)

Any queries related to past or future events should be returned in the appropriate format.

Example
query: Monday, 2024-12-02 12:30PM:  my gf is visiting on Tuesday
answer: add_entry("2024-12-03", "gf is visiting", None, ["girlfriend"])     # can guess the date of the next Tuesday based on the fact its Monday
query: Monday, 2024-12-02 12:30PM:  my moms coming over next week for a couple of nights
answer: add_entry("2024-12-09", "moms coming over", "2024-12-11", ["moms"])
query: Wednesday, 2024-12-04 12:30PM: dentist on 5th May
answer: add_entry("2025-05-05", "dentist")   # since its after May 2024, it's assumed to be 2025
query: what events do I have coming up?
answer: lookup_events()
query: when is mom visiting?
answer: lookup_events(people=["mom"])
query: what's happening next week?
answer: lookup_events("2024-01-15", "2024-01-21")      # Based on given date, guess dates for next Monday and Sunday
query: what's on the calendar after March?
answer: lookup_events("2024-03-01")
query: clear all events from January
answer: clear_events("2024-01-01", "2024-01-31")
query: delete everything after summer
answer: clear_events("2024-09-01")
query: wipe March and April clean
answer: clear_events("2024-03-01", "2024-04-30")

Return only the command to be executed as a raw string, no string delimiters
wrapping it, no yapping, no markdown, no fenced code blocks, what you return
will be passed to exec() directly after validation.
""".strip()



@migration
def m0x_events(db):
    """Create events table for tracking calendar events."""
    db["events"].create(
        {
            "id": str,
            "start_time": str,
            "end_time": str,
            "text": str,
            "people": str
         },
         pk="id"
    )


@migration
def m1x_prompt_in_events(db):
    """Add prompt column to events table."""
    db["events"].add_column("prompt", str)


def parse_command(text):
    """Validates and returns (function_name, args, kwargs)"""
    try:
        tree = ast.parse(text)
        call = tree.body[0].value  # Get the function call
        
        if not isinstance(call, ast.Call):
            return None
            
        func_name = call.func.id
        args = [ast.literal_eval(arg) for arg in call.args]
        kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
        
        return func_name, args, kwargs
    except Exception:
        return None


def parse_datetime(date_str):
    """Convert various date strings to datetime objects"""
    if date_str is None:
        return None
    # Add more formats as needed
    formats = ["%Y-%m-%d", "%Y-%m-%d %H:%M"]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def add_entry(start_time, text, end_time=None, people=None, prompt=None):
    """Add an entry to the calendar."""
    people = people or []
    people = ", ".join(people)
    db = sqlite_utils.Database(logs_path)
    migrate(db)
    db["events"].insert(
             {
                 "start_time": start_time,
                 "end_time": end_time or start_time,
                 "text": text,
                 "people": people,
                 "prompt": prompt
             }
         )


def clear_events(start_date: str = None, end_date: str = None) -> int:
    """Clear events from the calendar within the given date range.
    If only start_date is provided, clears events for just that day.
    Returns number of events deleted."""
    db = sqlite_utils.Database(logs_path)
    migrate(db)

    if not start_date and not end_date:
        response = input("Warning: This will delete ALL events. Are you sure? (y/N): ")
        if response.lower() != 'y':
            return 0
        return db["events"].delete_where()
    
    where = []
    where_args = []
    
    if start_date:
        where.append("start_time >= ?")
        where_args.append(start_date)
        # If no end_date provided, set it to same as start_date
        if not end_date:
            where.append("start_time <= ?")
            where_args.append(start_date)
        else:
            where.append("start_time <= ?")
            where_args.append(end_date)
        
    where_clause = " AND ".join(where)
    count =  db["events"].count_where(where_clause, where_args)
    db["events"].delete_where(where_clause, where_args)
    return count


def lookup_events(start_date: str = datetime.date.today().isoformat(), end_date: str = None, people: List = None, fancy: bool = True):
    query = "SELECT * FROM events WHERE start_time >= ?"
    params = [start_date]
    
    if end_date:
        query += " AND start_time <= ?"
        params.append(end_date)
        
    if people:
        query += " AND people LIKE ?"
        params.append(f"%{','.join(people)}%")

    query += "ORDER BY start_time ASC"

    db = sqlite_utils.Database(logs_path)
    migrate(db)
    events = list(db.query(query, params))
    
    if not events:
        print("No events found for this period.")
        return

    # Format the date range for the summary
    start_desc = datetime.datetime.strptime(start_date, "%Y-%m-%d").strftime("%B %d, %Y")
    if end_date:
        end_desc = datetime.datetime.strptime(end_date, "%Y-%m-%d").strftime("%B %d, %Y")
        period = f"between {start_desc} and {end_desc}"
    else:
        period = f"from {start_desc} onwards"

    # Create the summary
    if people:
        people_str = " and ".join(people)
        print(f"Found {len(events)} event(s) {period} involving {people_str}:")
    else:
        print(f"Found {len(events)} event(s) {period}:")

    # Format events into a list
    event_list = []
    for event in events:
        event_date = datetime.datetime.strptime(event['start_time'], "%Y-%m-%d").strftime("%B %d")
        if event['end_time'] and event['end_time'] != event['start_time']:
            end_date = datetime.datetime.strptime(event['end_time'], "%Y-%m-%d").strftime("%B %d")
            event_list.append(f"- {event_date} to {end_date}: {event['text']}")
        else:
            event_list.append(f"- {event_date}: {event['text']}")

    # Print the events
    print("\n".join(event_list))
    
    if fancy:
        # Create context for LLM
        context = f"Here are the events {period}:\n" + "\n".join(event_list)
        
        # Get LLM to summarize
        model = llm.get_model(get_default_model())
        result = model.prompt(SUMMARY_PROMPT.format(context=context))
        print("\nSummary:")
        print(result.text())


@llm.hookimpl
def register_commands(cli):
    @cli.group(
           cls=DefaultGroup,
           default='query',
           default_if_no_args=True
       )
    def calendar():
        """Manage your calendar events"""
        pass

    @calendar.command()
    @click.argument("args", nargs=-1)
    @click.option("--fancy/--no-fancy", default=True, help="Use LLM to generate natural language summaries")
    def query(args, fancy):
        """Query your calendar using natural language"""
        prompt = datetime.datetime.now().strftime('%A, %d %B %Y %I:%M%p %Z') + " ".join(args)
        model = llm.get_model(get_default_model())
        result = model.prompt(prompt, system=SYSTEM_PROMPT)
        
        print(result)
        parsed = parse_command(result.text())
        if parsed:
            func_name, args, kwargs = parsed
            if func_name == 'add_entry':
                add_entry(*args, **kwargs, prompt=prompt)
            if func_name == 'lookup_events':
                kwargs['fancy'] = fancy
                lookup_events(*args, **kwargs)
            if func_name == 'clear_events':
                count = clear_events(*args, **kwargs)
                if count > 0:
                    print(f"Deleted {count} event(s)")
                else:
                    print("No events found in that date range")

    @calendar.command()
    @click.option("--start", help="Start date (YYYY-MM-DD)")
    @click.option("--end", help="End date (YYYY-MM-DD)")
    def clear(start, end):
        """Clear events from the calendar"""
        try:
            count = clear_events(start, end)
            if count > 0:
                print(f"Deleted {count} event(s)")
            else:
                print("No events found in that date range")
        except ValueError as e:
            print(str(e))

    @calendar.command()
    def dump():
        """Print all events in the database"""
        db = sqlite_utils.Database(logs_path)
        migrate(db)
        events = db.query("SELECT * FROM events ORDER BY start_time")
        for event in events:
            print(f"Start: {event['start_time']}", end="")
            if event['end_time']:
                print(f" - End: {event['end_time']}", end="")
            print(f"\nEvent: {event['text']}")
            if event['people']:
                print(f"People: {event['people']}")
            print("---")
