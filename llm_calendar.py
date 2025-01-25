import datetime
import ast
import click
import llm
import subprocess
import sqlite_utils
from typing import List

from llm.migrations import migration, migrate
from llm.cli import get_default_model
from llm import user_dir


logs_path = user_dir() / "logs.db"


SYSTEM_PROMPT = """
Available tools:
- add_entry(start_time: str, text: str, end_time: str = None, people: Optional[List] = None)
- lookup_events(start_date: str = date.today().isoformat(), end_date: str = None, people: Optional[List] = None)

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


def lookup_events(start_date: str = datetime.date.today().isoformat(), end_date: str = None, people: List = None):
    query = "SELECT * FROM events WHERE start_time >= ?"
    params = [start_date]
    
    if end_date:
        query += " AND start_time <= ?"
        params.append(end_date)
        
    if people:
        query += " AND people LIKE ?"
        params.append(f"%{','.join(people)}%")

    db = sqlite_utils.Database(logs_path)
    migrate(db)
    events = db.query(query, params)
    for event in events:
        print(f"{event['start_time']}: {event['text']}")


@llm.hookimpl
def register_commands(cli):
    @cli.command()
    @click.argument("args", nargs=-1)
    def calendar(args):
        prompt = datetime.datetime.now().strftime('%A, %d %B %Y %I:%M%p %Z') + " ".join(args)
        model = llm.get_model(get_default_model())
        result = model.prompt(prompt, system=SYSTEM_PROMPT)
        
        parsed = parse_command(result.text())
        if parsed:
            func_name, args, kwargs = parsed
            if func_name == 'add_entry':
                add_entry(*args, **kwargs, prompt=prompt)
            if func_name == 'lookup_events':
                lookup_events(*args, **kwargs)

    @cli.command()
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