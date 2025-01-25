import pytest
import datetime
import sqlite_utils
import os
from llm_calendar import (
    parse_command,
    add_entry,
    lookup_events,
    logs_path
)

@pytest.fixture
def test_db():
    # Use an in-memory database for testing
    logs_path = lambda: ":memory:"
    db = sqlite_utils.Database(logs_path())
    
    # Create tables
    db["events"].create(
        {
            "id": str,
            "start_time": str,
            "end_time": str,
            "text": str,
            "people": str,
            "prompt": str
        },
        pk="id"
    )
    
    yield db
    

def test_parse_command():
    # Test valid commands
    assert parse_command('add_entry("2024-01-20", "test event")') == (
        'add_entry',
        ['2024-01-20', 'test event'],
        {}
    )
    
    assert parse_command('lookup_events("2024-01-01", "2024-12-31")') == (
        'lookup_events',
        ['2024-01-01', '2024-12-31'],
        {}
    )
    
    # Test invalid commands
    assert parse_command('invalid command') is None
    assert parse_command('rm -rf /') is None


def test_add_entry(test_db):
    # Test basic event addition
    add_entry("2024-01-20", "Test Event")
    events = list(test_db.query("SELECT * FROM events"))
    assert len(events) == 1
    assert events[0]["text"] == "Test Event"
    assert events[0]["start_time"] == "2024-01-20"
    
    # Test event with people
    add_entry("2024-01-21", "Family Dinner", people=["mom", "dad"])
    events = list(test_db.query("SELECT * FROM events WHERE people LIKE ?", ["%mom%"]))
    assert len(events) == 1
    assert "mom" in events[0]["people"]
    assert "dad" in events[0]["people"]


def test_lookup_events(test_db, capsys):
    # Add some test events
    add_entry("2024-01-20", "Event 1")
    add_entry("2024-01-21", "Event 2", people=["Alice"])
    add_entry("2024-01-22", "Event 3", "2024-01-24")
    
    # Test basic lookup
    lookup_events("2024-01-20", "2024-01-22", fancy=False)
    captured = capsys.readouterr()
    assert "Event 1" in captured.out
    assert "Event 2" in captured.out
    assert "Event 3" in captured.out
    
    # Test people filter
    lookup_events("2024-01-20", "2024-01-22", people=["Alice"], fancy=False)
    captured = capsys.readouterr()
    assert "Event 1" not in captured.out
    assert "Event 2" in captured.out
    assert "Event 3" not in captured.out
